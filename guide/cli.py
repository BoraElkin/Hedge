"""CLI entry point for Guide."""

import uvicorn

from guide.config import get_settings


def main():
    """Run the Guide server."""
    settings = get_settings()
    print(f"""
╔═══════════════════════════════════════════════════════════╗
║                         GUIDE                              ║
║          Real-time AI guidance for physical work           ║
╠═══════════════════════════════════════════════════════════╣
║  Server: http://{settings.host}:{settings.port}                          ║
║  Demo UI: http://{settings.host}:{settings.port}/demo                    ║
║  API Docs: http://{settings.host}:{settings.port}/docs                   ║
╚═══════════════════════════════════════════════════════════╝
    """)

    uvicorn.run(
        "guide.api.app:app",
        host=settings.host,
        port=settings.port,
        reload=(settings.environment == "development"),
    )


if __name__ == "__main__":
    main()
