import os

TEST_ENV = {
    "LINE_CHANNEL_SECRET": "test-secret",
    "LINE_CHANNEL_ACCESS_TOKEN": "test-access-token",
    "LINE_LOGIN_CHANNEL_ID": "test-login-channel",
    "POSTGRES_USER": "test",
    "POSTGRES_PASSWORD": "test",
    "POSTGRES_HOST": "localhost",
    "POSTGRES_PORT": "5432",
    "POSTGRES_DB": "test",
}

for key, value in TEST_ENV.items():
    os.environ.setdefault(key, value)
