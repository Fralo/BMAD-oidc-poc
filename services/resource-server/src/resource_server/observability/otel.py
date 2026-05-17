import logging

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from resource_server.core.config import AppSettings

logger = logging.getLogger(__name__)


def setup_otel(settings: AppSettings) -> TracerProvider:
    resource = Resource(attributes={"service.name": settings.otel_service_name})
    provider = TracerProvider(resource=resource)

    if settings.otel_export_enabled:
        exporter = OTLPSpanExporter(
            endpoint=settings.otel_exporter_endpoint,
            insecure=True,
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        logger.info("OTEL trace export enabled -> %s", settings.otel_exporter_endpoint)
    else:
        logger.info("OTEL trace export disabled")

    trace.set_tracer_provider(provider)
    return provider
