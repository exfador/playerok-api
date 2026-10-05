set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_VER="3.11.8"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"

if [ "${EUID:-$(id -u)}" -ne 0 ]; then
    SUDO="sudo"
else
    SUDO=""
fi

echo "=== Каталог проекта: ${PROJECT_DIR} ==="
cd "${PROJECT_DIR}"

if [ ! -f requirements.lock ] || [ ! -f main.py ]; then
    echo "Скрипт нужно запускать из папки проекта (рядом с main.py и requirements.lock)."
    exit 1
fi

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "=== Python 3.11 не найден, устанавливаю ==="
    export DEBIAN_FRONTEND=noninteractive
    ${SUDO} apt-get update -y
    if ${SUDO} apt-get install -y python3.11 python3.11-venv 2>/dev/null; then
        PYTHON_BIN="python3.11"
    else
        ${SUDO} apt-get install -y build-essential zlib1g-dev libncurses5-dev libgdbm-dev libnss3-dev \
            libssl-dev libreadline-dev libffi-dev libsqlite3-dev wget libbz2-dev ca-certificates tar xz-utils
        BUILD_DIR="$(mktemp -d)"
        trap 'rm -rf "${BUILD_DIR}"' EXIT
        cd "${BUILD_DIR}"
        wget -q --show-progress "https://www.python.org/ftp/python/${PYTHON_VER}/Python-${PYTHON_VER}.tgz"
        tar -xf "Python-${PYTHON_VER}.tgz"
        cd "Python-${PYTHON_VER}"
        ./configure --enable-optimizations
        make -j "$(nproc)"
        ${SUDO} make altinstall
        cd "${PROJECT_DIR}"
        PYTHON_BIN="python3.11"
    fi
fi

echo "=== Виртуальное окружение .venv ==="
if [ ! -d .venv ]; then
    "${PYTHON_BIN}" -m venv .venv
fi
.venv/bin/python -m pip install --upgrade pip -q
.venv/bin/python -m pip install -r requirements.lock

mkdir -p conf db logs ext
chmod 700 conf db 2>/dev/null || true

echo ""
echo "=============================================="
echo "Готово. Существующие conf/, db/, logs/ и ext/ не изменялись."
echo "=============================================="
echo ""
echo "Запуск:"
echo "  cd ${PROJECT_DIR}"
echo "  .venv/bin/python main.py"
echo ""
echo "Для работы 24/7 удобно использовать screen или systemd:"
echo "  screen -S playerok .venv/bin/python main.py"
echo ""
