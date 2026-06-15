"""QuantTrade command-line interface.

Usage::

    python -m quanttrade.cli backtest --strategy ma_crossover --symbols AAPL,MSFT
    python -m quanttrade.cli scan --symbols AAPL,MSFT,TSLA
    python -m quanttrade.cli optimize --strategy ma_crossover --symbols AAPL
    python -m quanttrade.cli init-db
    python -m quanttrade.cli serve
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime

from .core.config import get_config
from .core.logging_config import setup_logging
from .data import create_data_provider


def _parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")


def _load_data(symbols: list[str], start: datetime, end: datetime, provider: str):
    prov = create_data_provider(provider)
    return {s: prov.get_historical_bars(s, start, end) for s in symbols}


def cmd_backtest(args) -> None:
    from .backtest import BacktestEngine
    from .risk import RiskLimits, RiskManager
    from .strategies import StrategyRegistry  # noqa: F401  (ensures registration)
    import quanttrade.strategies  # noqa: F401

    data = _load_data(args.symbols.split(","), _parse_date(args.start),
                      _parse_date(args.end), args.provider)
    strategy = StrategyRegistry.create(args.strategy)
    risk = RiskManager(RiskLimits.from_config(get_config()))
    engine = BacktestEngine(strategy, starting_cash=args.cash, risk_manager=risk)
    result = engine.run(data)
    print(json.dumps(result.summary(), indent=2))


def cmd_scan(args) -> None:
    from .scanner import MarketScanner
    scanner = MarketScanner(create_data_provider(args.provider))
    results = scanner.scan(args.symbols.split(","), top_n=args.top)
    for r in results:
        print(f"{r.symbol:6s} score={r.score:8.2f}  {r.price:10.2f}  "
              f"{r.change_pct:+.2%}  {r.reason}")


def cmd_optimize(args) -> None:
    from .backtest import GridSearchOptimizer
    from .strategies import StrategyRegistry  # noqa: F401
    import quanttrade.strategies  # noqa: F401

    data = _load_data(args.symbols.split(","), _parse_date(args.start),
                      _parse_date(args.end), args.provider)
    strategy_cls = StrategyRegistry._registry[args.strategy.lower()]
    grid = json.loads(args.grid)
    opt = GridSearchOptimizer(strategy_cls, grid)
    res = opt.optimize(data)
    print("Best params:", json.dumps(res.best_params))
    print("Best score :", round(res.best_score, 4))


def cmd_init_db(args) -> None:
    from .persistence import Database
    db = Database(args.url) if args.url else Database()
    db.create_all()
    print("Database initialised.")


def cmd_serve(args) -> None:
    try:
        import uvicorn
    except ImportError:
        raise SystemExit("Install web extras: pip install fastapi uvicorn")
    cfg = get_config()
    uvicorn.run("quanttrade.api.app:app", host=args.host or cfg.get("api.host"),
                port=args.port or cfg.get("api.port"), reload=args.reload)


def cmd_list_strategies(args) -> None:
    import quanttrade.strategies  # noqa: F401
    from .strategies import StrategyRegistry
    print("\n".join(StrategyRegistry.available()))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="quanttrade", description="QuantTrade CLI")
    p.add_argument("--provider", default="synthetic", help="market data provider")
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser("backtest", help="run a backtest")
    b.add_argument("--strategy", default="ma_crossover")
    b.add_argument("--symbols", default="AAPL,MSFT")
    b.add_argument("--start", default="2021-01-01")
    b.add_argument("--end", default="2023-01-01")
    b.add_argument("--cash", type=float, default=100_000.0)
    b.set_defaults(func=cmd_backtest)

    s = sub.add_parser("scan", help="scan a universe")
    s.add_argument("--symbols", default="AAPL,MSFT,TSLA,NVDA,SPY")
    s.add_argument("--top", type=int, default=10)
    s.set_defaults(func=cmd_scan)

    o = sub.add_parser("optimize", help="grid-search a strategy")
    o.add_argument("--strategy", default="ma_crossover")
    o.add_argument("--symbols", default="AAPL")
    o.add_argument("--start", default="2020-01-01")
    o.add_argument("--end", default="2023-01-01")
    o.add_argument("--grid", default='{"fast":[5,10,20],"slow":[30,50,100]}')
    o.set_defaults(func=cmd_optimize)

    d = sub.add_parser("init-db", help="create database tables")
    d.add_argument("--url", default="")
    d.set_defaults(func=cmd_init_db)

    sv = sub.add_parser("serve", help="run the API server")
    sv.add_argument("--host", default="")
    sv.add_argument("--port", type=int, default=0)
    sv.add_argument("--reload", action="store_true")
    sv.set_defaults(func=cmd_serve)

    sub.add_parser("strategies", help="list available strategies").set_defaults(
        func=cmd_list_strategies)
    return p


def main(argv: list[str] | None = None) -> None:
    setup_logging(level=get_config().get("logging.level", "INFO"))
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":  # pragma: no cover
    main()
