from collections.abc import Iterable
from prometheus_client.core import GaugeMetricFamily, Metric
from prometheus_client.registry import Collector
from sqlalchemy import select, func
from packages.common.db import Session, Work, Worker, Instance, Delivery, Job, ExecutionAttempt, now
from packages.common.service import reconcile


class PlatformCollector(Collector):
    def describe(self) -> Iterable[Metric]:
        return []

    def collect(self) -> Iterable[Metric]:
        with Session.begin() as s:
            counts = GaugeMetricFamily("inferenceflow_requests", "Request states", labels=["status"])
            for state, count in s.execute(select(Work.status, func.count()).group_by(Work.status)):
                counts.add_metric([state], count)
            yield counts
            metrics: dict[str, float | int | None] = {
                "inferenceflow_wallet_drift": len(reconcile(s)),
                "inferenceflow_late_requests": s.scalar(
                    select(func.count()).select_from(Work).where(Work.late.is_(True))
                ),
                "inferenceflow_successful_input_tokens": s.scalar(
                    select(func.coalesce(func.sum(Work.input_tokens), 0))
                ),
                "inferenceflow_successful_output_tokens": s.scalar(
                    select(func.coalesce(func.sum(Work.output_tokens), 0))
                ),
                "inferenceflow_captured_micro_usd": s.scalar(select(func.coalesce(func.sum(Work.captured), 0))),
                "inferenceflow_webhook_pending": s.scalar(
                    select(func.count()).select_from(Delivery).where(Delivery.delivered.is_(False))
                ),
                "inferenceflow_active_instances": s.scalar(
                    select(func.count()).select_from(Instance).where(Instance.terminated.is_(False))
                ),
                "inferenceflow_dispatched_attempts": s.scalar(select(func.count()).select_from(ExecutionAttempt)),
            }
            from packages.common.performance import operations_report
            report = operations_report(s)
            perf, plan, econ = report["performance"], report["capacity"], report["economics"]
            for name in ("queue_backlog_requests", "estimated_deadline_risk_jobs", "successful_within_60_minutes",
                         "successful_deadline_misses", "deadline_attainment", "sub_hour_attainment",
                         "tokens_per_second_wall_clock_24h"):
                if perf[name] is not None:
                    metrics["inferenceflow_scheduling_" + name] = perf[name]
            for p, value in perf["end_to_end_seconds"].items():
                if value is not None:
                    metrics["inferenceflow_job_latency_seconds_" + p] = value
            metrics["inferenceflow_capacity_recommended_gpus"] = plan["required_gpus_estimate"]
            metrics["inferenceflow_gpu_estimated_cost_micro_usd"] = econ["estimated_cost_micro_usd"]
            for field in ("observed_active_seconds", "observed_idle_seconds"):
                metrics["inferenceflow_gpu_" + field] = sum(r[field] for r in econ["instances"])
            workers = list(s.scalars(select(Worker)))
            for metric_name, field in [
                ("inferenceflow_gpu_utilization", "gpu_utilization"),
                ("inferenceflow_kv_cache_usage", "kv_cache_usage"),
                ("inferenceflow_worker_http_inflight", "worker_http_inflight"),
                ("inferenceflow_worker_http_peak_inflight", "worker_http_peak_inflight"),
                ("inferenceflow_worker_http_overlap_seconds", "worker_http_overlap_seconds"),
                ("inferenceflow_engine_running", "engine_running"),
                ("inferenceflow_engine_waiting", "engine_waiting"),
                ("inferenceflow_engine_prompt_tokens_total", "engine_prompt_tokens_total"),
                ("inferenceflow_engine_output_tokens_total", "engine_output_tokens_total"),
                ("inferenceflow_gpu_memory_used_mib", "gpu_memory_used_mib"),
                ("inferenceflow_gpu_memory_total_mib", "gpu_memory_total_mib"),
                ("inferenceflow_worker_http_idle_seconds", "worker_http_idle_seconds"),
                ("inferenceflow_worker_observed_input_tokens_per_second", "observed_input_tokens_per_second"),
                ("inferenceflow_worker_observed_output_tokens_per_second", "observed_output_tokens_per_second"),
            ]:
                gauge = GaugeMetricFamily(metric_name, metric_name, labels=["worker"])
                for worker in workers:
                    from packages.common.scheduling import telemetry
                    data, fresh = telemetry(worker, now())
                    value = data.get(field)
                    if value is not None and fresh:
                        gauge.add_metric([worker.id], value)
                yield gauge
            capacity = sum(w.capacity for w in workers if (now() - w.heartbeat).total_seconds() < 90)
            busy = s.scalar(select(func.count()).select_from(Work).where(Work.status.in_(["leased", "running"]))) or 0
            metrics["inferenceflow_worker_slot_utilization"] = busy / capacity if capacity else 0
            oldest = s.scalar(
                select(func.min(Job.created_at)).join(Work, Work.job_id == Job.id).where(Work.status == "queued")
            )
            metrics["inferenceflow_oldest_queue_age_seconds"] = (now() - oldest).total_seconds() if oldest else 0

            metrics["inferenceflow_worker_max_heartbeat_age_seconds"] = max(
                ((now() - w.heartbeat).total_seconds() for w in workers), default=0
            )
            for name, value in metrics.items():
                scheduling_metric = name.startswith(("inferenceflow_scheduling_", "inferenceflow_job_latency_", "inferenceflow_capacity_", "inferenceflow_gpu_estimated_", "inferenceflow_gpu_observed_"))
                modes = ",".join(perf["measurement_modes"]) or "no_observations"
                gauge = GaugeMetricFamily(name, name, labels=["measurement_modes"] if scheduling_metric else [])
                gauge.add_metric([modes] if scheduling_metric else [], float(value or 0))
                yield gauge
