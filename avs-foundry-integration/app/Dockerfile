FROM python:3.12-slim-bookworm

# Microsoft ODBC Driver 18 (for SQL Server sources). bookworm avoids the
# SHA1/sqv signature issue seen on newer Debian bases.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl gnupg apt-transport-https ca-certificates \
    && curl -sSL https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb -o /tmp/pmc.deb \
    && dpkg -i /tmp/pmc.deb && rm /tmp/pmc.deb \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 unixodbc-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

EXPOSE 8000
CMD ["python", "mcp_server.py"]
