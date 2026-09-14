import uvicorn

from api.utils_api import app

__all__ = ["app"]


def main():
    uvicorn.run("api.utils_api:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()
