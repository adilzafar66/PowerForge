"""Document-extraction queue tasks; classification retains its own queue and adapter."""

from uuid import UUID

from sqlalchemy.orm import sessionmaker

from extraction_worker.celery_app import _engine, celery_app
from powerforge_ai.extraction import ErrorCode, ExtractionProvider, ProviderFailure
from powerforge_document_processing.storage.factory import build_s3_storage
from powerforge_extraction.enqueue import QUEUE, RECOVER_TASK, UNIT_TASK, CeleryExtractionEnqueue
from powerforge_extraction.execution import execute_unit
from powerforge_extraction.fake import FakeEngineeringProvider, FakeExtractionProvider
from powerforge_extraction.orchestration import Claim, ExtractionCoordinator
from powerforge_extraction.production_profiles import ProductionProfile
from powerforge_extraction.profiles import EngineeringProfile
from powerforge_extraction.table_profiles import TableProfile
from powerforge_shared.config import get_settings


def provider_for(claim: Claim) -> ExtractionProvider:
    if claim.profile.provider == "fake":
        if isinstance(claim.profile, TableProfile):
            from powerforge_extraction.table_fake import FakeTableProvider

            return FakeTableProvider(claim.profile.fake_scenario)
        if isinstance(claim.profile, EngineeringProfile):
            return FakeEngineeringProvider(claim.profile.fake_scenario)
        return FakeExtractionProvider(claim.profile.fake_scenario)
    if isinstance(claim.profile, EngineeringProfile) and not isinstance(
        claim.profile, ProductionProfile
    ):
        raise ProviderFailure(ErrorCode.DISABLED)
    from extraction_worker.openai_extraction import OpenAIExtractionProvider

    return OpenAIExtractionProvider(
        get_settings(),
        profile=claim.profile
        if isinstance(claim.profile, (ProductionProfile, TableProfile))
        else None,
    )


@celery_app.task(
    name=UNIT_TASK,
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=330,
    time_limit=345,
    ignore_result=True,
)
def execute_work_unit(unit_id: str) -> None:
    settings = get_settings()
    factory = sessionmaker(bind=_engine(), autoflush=False, expire_on_commit=False)
    execute_unit(UUID(unit_id), factory, build_s3_storage(settings), settings, provider_for)
    with factory.begin() as session:
        ExtractionCoordinator(session, settings).dispatch(
            CeleryExtractionEnqueue(celery_app), purpose=None
        )


@celery_app.task(name=RECOVER_TASK, ignore_result=True, soft_time_limit=60, time_limit=90)
def reconcile_extraction() -> None:
    settings = get_settings()
    factory = sessionmaker(bind=_engine(), autoflush=False, expire_on_commit=False)
    with factory.begin() as session:
        ExtractionCoordinator(session, settings).reconcile()
    with factory.begin() as session:
        ExtractionCoordinator(session, settings).dispatch(
            CeleryExtractionEnqueue(celery_app), purpose=None
        )


celery_app.conf.beat_schedule = {
    **(celery_app.conf.beat_schedule or {}),
    "reconcile-document-extraction": {
        "task": RECOVER_TASK,
        "schedule": get_settings().extraction_recovery_interval_seconds,
        "options": {"queue": QUEUE},
    },
}


@celery_app.task(
    name="source_enrichment.execute_unit",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=135,
    time_limit=150,
    ignore_result=True,
)
def execute_source_unit(unit_id: str) -> None:
    from extraction_worker.tesseract import TesseractProvider
    from powerforge_extraction.enrichment_execution import execute_preparation

    settings = get_settings()
    factory = sessionmaker(bind=_engine(), autoflush=False, expire_on_commit=False)
    execute_preparation(
        UUID(unit_id),
        factory,
        build_s3_storage(settings),
        settings,
        lambda: TesseractProvider(
            settings.enrichment_tesseract_binary, settings.enrichment_tessdata_directory
        ),
    )
    with factory.begin() as session:
        ExtractionCoordinator(session, settings).dispatch(
            CeleryExtractionEnqueue(celery_app), purpose=None
        )


if get_settings().enrichment_enabled:
    celery_app.conf.beat_schedule = {
        **celery_app.conf.beat_schedule,
        "reconcile-local-source-enrichment": {
            "task": RECOVER_TASK,
            "schedule": get_settings().extraction_recovery_interval_seconds,
            "options": {"queue": "source_enrichment"},
        },
    }
