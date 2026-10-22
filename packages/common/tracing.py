"""Optional OTLP tracing. Prompts, completions and credentials are never span attributes."""

from packages.common.config import settings


def instrument(app):
    endpoint = settings().otel_exporter_otlp_endpoint
    if not endpoint:
        return
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    provider = TracerProvider(resource=Resource.create({"service.name": "inferenceflow-api"}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint.rstrip("/") + "/v1/traces")))
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider, excluded_urls="healthz,readyz,metrics")
