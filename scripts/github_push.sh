#!/usr/bin/env bash
# Первичная публикация content-factory на GitHub
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -d .git ]]; then
  git init -b main
fi

git add -A
git status

if git diff --cached --quiet; then
  echo "Нечего коммитить."
  exit 0
fi

git commit -m "$(cat <<'EOF'
Add Content Factory microservice with Streamlit admin panel.

RSS ingest, VK/Telegram publishing, approval workflow, and Streamlit Cloud deployment config.
EOF
)"

echo ""
echo "Далее создайте репозиторий на GitHub и выполните:"
echo "  git remote add origin https://github.com/USER/content-factory.git"
echo "  git push -u origin main"
echo ""
echo "Streamlit Cloud: main file = admin/app.py"
