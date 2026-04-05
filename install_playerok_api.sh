

set -euo pipefail

REPO="exfador/playerok-api"
INSTALL_DIR="${INSTALL_DIR:-/root/playerok-api}"
PYTHON_VER="3.11.8"

if [ "${EUID:-}" -ne 0 ]; then
    echo "Запустите с правами root: sudo bash install_playerok_api.sh"
    exit 1
fi

echo "=== 1. Обновление системы и зависимости для сборки Python ==="
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y build-essential zlib1g-dev libncurses5-dev libgdbm-dev libnss3-dev \
    libssl-dev libreadline-dev libffi-dev libsqlite3-dev wget libbz2-dev \
    ca-certificates gnupg tar xz-utils

echo "=== 2. Установка Python ${PYTHON_VER} (altinstall) ==="
cd /tmp
rm -rf "Python-${PYTHON_VER}"
wget -q --show-progress "https://www.python.org/ftp/python/${PYTHON_VER}/Python-${PYTHON_VER}.tgz"
tar -xf "Python-${PYTHON_VER}.tgz"
cd "Python-${PYTHON_VER}"
./configure --enable-optimizations
make -j "$(nproc)"
make altinstall
cd /

echo "=== 3. curl, jq, screen ==="
apt-get install -y curl jq screen

echo "=== 4. pip для python3.11 ==="
if ! command -v python3.11 >/dev/null 2>&1; then
    echo "python3.11 не найден после установки"
    exit 1
fi
curl -sS https://bootstrap.pypa.io/get-pip.py | python3.11 - 2>/dev/null || \
    curl -sS https://bootstrap.pypa.io/get-pip.py | python3.11 - --break-system-packages
python3.11 -m pip install --upgrade pip -q || true

echo "=== 5. Русская локаль (опционально) ==="
apt-get install -y language-pack-ru language-pack-gnome-ru 2>/dev/null || true
update-locale LANG=ru_RU.UTF-8 2>/dev/null || true

echo "=== 6. Версия для установки (релиз или тег) ==="
API_REL="https://api.github.com/repos/${REPO}/releases/latest"
API_TAGS="https://api.github.com/repos/${REPO}/tags"

TAG=""
REL_JSON="$(curl -sS "$API_REL")"
TAG="$(echo "$REL_JSON" | jq -r '.tag_name // empty')"
if [[ -z "$TAG" || "$TAG" == "null" ]]; then
    echo "Активного GitHub Release нет, беру последний тег из репозитория…"
    TAG="$(curl -sS "$API_TAGS" | jq -r '.[0].name // empty')"
fi
if [[ -z "$TAG" || "$TAG" == "null" ]]; then
    echo "Не удалось определить тег (проверьте сеть и имя репозитория ${REPO})."
    exit 1
fi

echo "Устанавливаю версию: ${TAG}"

ARCHIVE_NAME="playerok-api-${TAG}.tar.gz"
ARCHIVE_URL="https://github.com/${REPO}/archive/refs/tags/${TAG}.tar.gz"

echo "=== 7. Скачивание архива ==="
cd /tmp
rm -f "$ARCHIVE_NAME"
wget -q --show-progress -O "$ARCHIVE_NAME" "$ARCHIVE_URL"

echo "=== 8. Распаковка в ${INSTALL_DIR} ==="
rm -rf "${INSTALL_DIR}"
mkdir -p "${INSTALL_DIR}"
tar -xzf "$ARCHIVE_NAME" -C "${INSTALL_DIR}" --strip-components=1
rm -f "$ARCHIVE_NAME"

echo "=== 9. Зависимости Python (requirements.txt) ==="
cd "$INSTALL_DIR"
if [ -f requirements.txt ]; then
    python3.11 -m pip install -r requirements.txt
else
    echo "Внимание: requirements.txt не найден в ${INSTALL_DIR}"
fi

echo ""
echo "=============================================="
echo "Установка CXH Playerok завершена"
echo "=============================================="
echo ""
echo "Каталог: ${INSTALL_DIR}"
echo "Версия:  ${TAG}"
echo ""
echo "Запуск (через screen):"
echo "  screen -S playerok"
echo "  cd ${INSTALL_DIR}"
echo "  python3.11 main.py"
echo ""
echo "Отсоединиться от screen: Ctrl+A, затем D"
echo "Вернуться: screen -r playerok"
echo ""
echo "Первый запуск: мастер в консоли спросит токен бота, пароль, JWT Playerok и т.д."
echo ""
