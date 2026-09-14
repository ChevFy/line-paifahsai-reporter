import uvicorn

from api.utils_api import app
from config.config import settings

__all__ = ["app"]


def start_ngrok() -> str:
    from pyngrok import conf, ngrok

    if settings.NGROK_AUTH_TOKEN:
        conf.get_default().auth_token = settings.NGROK_AUTH_TOKEN

    tunnel = ngrok.connect(settings.PORT, "http")
    print(f"ngrok tunnel: {tunnel.public_url} -> http://127.0.0.1:{settings.PORT}")
    print(f"LINE webhook URL: {tunnel.public_url}/webhook")
    return tunnel.public_url


def main():
    if settings.USE_NGROK:
        start_ngrok()

    uvicorn.run(
        "api.utils_api:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
    )


if __name__ == "__main__":
    main()
