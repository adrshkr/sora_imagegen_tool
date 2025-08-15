# syntax=docker/dockerfile:1.7
FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir uv

FROM base AS builder
WORKDIR /app
COPY pyproject.toml .
RUN uv venv && uv pip install --system --no-cache-dir -r requirements.txt
COPY . .
RUN uv pip install --system --no-cache-dir .

FROM base AS runtime
WORKDIR /app
RUN useradd -m appuser || adduser -D appuser || true
USER appuser
COPY --from=builder /opt/pysetup/.venv /opt/pysetup/.venv
ENV PATH="/opt/pysetup/.venv/bin:C:\Program Files\Git\mingw64\bin;C:\Program Files\Git\usr\bin;C:\Users\adars\bin;C:\Users\adars\miniconda3\envs\PythonProject;C:\Users\adars\miniconda3\envs\PythonProject\Library\mingw-w64\bin;C:\Users\adars\miniconda3\envs\PythonProject\Library\usr\bin;C:\Users\adars\miniconda3\envs\PythonProject\Library\bin;C:\Users\adars\miniconda3\envs\PythonProject\Scripts;C:\Users\adars\miniconda3\envs\PythonProject\bin;C:\Users\adars\miniconda3\condabin;C:\Windows\system32;C:\Windows;C:\Windows\System32\Wbem;C:\Windows\System32\WindowsPowerShell\v1.0;C:\Windows\System32\OpenSSH;C:\Program Files (x86)\NVIDIA Corporation\PhysX\Common;C:\Program Files\Cloudflare\Cloudflare WARP;C:\Program Files (x86)\Windows Kits\10\Windows Performance Toolkit;C:\Program Files\dotnet;C:\Program Files\NVIDIA Corporation\NVIDIA app\NvDLISR;C:\WINDOWS\system32;C:\WINDOWS;C:\WINDOWS\System32\Wbem;C:\WINDOWS\System32\WindowsPowerShell\v1.0;C:\WINDOWS\System32\OpenSSH;C:\Program Files\Git\cmd;C:\Program Files\Amazon\AWSCLIV2;C:\Program Files\GitHub CLI;C:\Program Files\Docker\Docker\resources\bin;C:\Users\adars\scoop\shims;C:\Users\adars\AppData\Local\Programs\Python\Python313\Scripts;C:\Users\adars\AppData\Local\Programs\Python\Python313;C:\Users\adars\AppData\Local\Microsoft\WindowsApps;C:\Users\adars\.dotnet\tools;C:\Users\adars\AppData\Local\GitHubDesktop\bin;C:\Users\adars\AppData\Local\Programs\Microsoft VS Code\bin;C:\Program Files\JetBrains\JetBrains Rider 2024.1.4\bin;.;C:\Program Files\JetBrains\PyCharm Community Edition 2025.1.3.1\bin;.;C:\Users\adars\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin;C:\Program Files\JetBrains\PyCharm 2025.2.0.1\bin"
ENTRYPOINT ["sora_imagegen_tool"]
CMD ["--name", "world from container"]
