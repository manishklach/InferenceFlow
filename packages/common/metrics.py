import json
from collections.abc import Iterable
from prometheus_client.core import GaugeMetricFamily, Metric
from prometheus_client.registry import Collector
from sqlalchemy import select, func
from packages.common.db import Session, Work, Worker, Instance, Delivery, Job, now
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
            }
            workers = list(s.scalars(select(Worker)))
            for metric_name, field in [
                ("inferenceflow_gpu_utilization", "gpu_utilization"),
                ("inferenceflow_kv_cache_usage", "kv_cache_usage"),
            ]:
                gauge = GaugeMetricFamily(metric_name, metric_name, labels=["worker"])
                for worker in workers:
                    value = json.loads(worker.telemetry or "{}").get(field)
                    if value is not None:
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
                gauge = GaugeMetricFamily(name, name)
                gauge.add_metric([], float(value or 0))
                yield gauge
