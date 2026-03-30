from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.alerts.service import AlertService
from app.config.settings import Settings
from app.contracts.client import ArbExecutorClient
from app.exchanges.factory import build_cex_adapters, build_hyperevm_dex_adapters, build_shadow_dex_adapters
from app.execution.live import LiveDryRunExecutionEngine
from app.execution.paper import PaperExecutionEngine
from app.health.collector import HealthCollector
from app.jobs.runner import BotRunner
from app.quote_engine.edge import ModeledEdgeCalculator
from app.quote_engine.engine import HyperDexDexQuoteEngine, ShadowCexDexQuoteEngine
from app.risk.manager import GlobalRiskManager


@dataclass(slots=True)
class AppState:
    settings: Settings
    session_factory: async_sessionmaker
    alert_service: AlertService
    risk_manager: GlobalRiskManager
    paper_engine: PaperExecutionEngine
    live_engine: LiveDryRunExecutionEngine
    health_collector: HealthCollector
    runner: BotRunner


def build_app_state(settings: Settings, session_factory: async_sessionmaker) -> AppState:
    alert_service = AlertService(settings.discord_webhook_url)
    risk_manager = GlobalRiskManager(settings)
    health_collector = HealthCollector()

    edge = ModeledEdgeCalculator(settings)
    hyper_dex = build_hyperevm_dex_adapters(settings)
    cex = build_cex_adapters(settings)
    shadow_dex = build_shadow_dex_adapters(settings)

    hyper_engine = HyperDexDexQuoteEngine(settings, edge, hyper_dex)
    shadow_engine = ShadowCexDexQuoteEngine(settings, edge, cex, shadow_dex)

    paper_engine = PaperExecutionEngine()
    live_engine = LiveDryRunExecutionEngine(settings, arb_client=ArbExecutorClient(settings))

    runner = BotRunner(
        settings=settings,
        session_factory=session_factory,
        alert_service=alert_service,
        risk_manager=risk_manager,
        hyper_engine=hyper_engine,
        shadow_engine=shadow_engine,
        paper_engine=paper_engine,
        live_engine=live_engine,
        health_collector=health_collector,
    )

    return AppState(
        settings=settings,
        session_factory=session_factory,
        alert_service=alert_service,
        risk_manager=risk_manager,
        paper_engine=paper_engine,
        live_engine=live_engine,
        health_collector=health_collector,
        runner=runner,
    )
