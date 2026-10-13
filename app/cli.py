"""
Qastroute AI - Command Line Interface (CLI).
Manage, inspect, and benchmark the Universal Gateway directly from your terminal.
"""

import sys
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import argparse
import json
import uvicorn
from .router import router, MODEL_CATALOG
from .cache import cache

def cmd_start(args):
    print(f"[*] Starting Qastroute AI Universal Gateway on http://{args.host}:{args.port}...")
    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)

def cmd_models(args):
    print("\n" + "="*70)
    print("🚀 QASTROUTE AI — SUPPORTED MODEL CATALOG")
    print("="*70)
    for model_id, info in MODEL_CATALOG.items():
        print(f"  • {model_id:<20} | {info.get('tier', 'balanced'):<15} | ${info.get('cost_per_m', 5.0):<5.2f}/M | {info.get('description')}")
    print("="*70 + "\n")

def cmd_test_route(args):
    prompt = args.prompt
    tier, target_model = router.classify_complexity(prompt)
    info = MODEL_CATALOG[target_model]
    print("\n" + "="*60)
    print("🧭 QASTROUTE AI SMART ROUTER SIMULATION")
    print("="*60)
    print(f"Input Prompt:    '{prompt[:70]}...'")
    print(f"Classified Tier: {tier.upper()}")
    print(f"Selected Model:  {target_model} ({info.get('description')})")
    print(f"Estimated Cost:  ${info.get('cost_per_m'):.2f} / 1M tokens")
    print(f"Savings Ratio:   ~{round((1 - info.get('cost_per_m') / 20.0) * 100, 1)}% vs. Frontier Baseline")
    print("="*60 + "\n")

def main():
    parser = argparse.ArgumentParser(description="Qastroute AI - Universal Gateway CLI")
    subparsers = parser.add_subparsers(dest="subcommand", help="Available commands")

    # start
    p_start = subparsers.add_parser("start", help="Start the gateway server")
    p_start.add_argument("--host", default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
    p_start.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000)")
    p_start.add_argument("--reload", action="store_true", help="Enable auto-reload")

    # models
    p_models = subparsers.add_parser("models", help="List all supported models and pricing tiers")

    # route
    p_route = subparsers.add_parser("route", help="Simulate semantic routing for a prompt")
    p_route.add_argument("prompt", help="Prompt text to test")

    args = parser.parse_args()

    if args.subcommand == "start":
        cmd_start(args)
    elif args.subcommand == "models":
        cmd_models(args)
    elif args.subcommand == "route":
        cmd_test_route(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
