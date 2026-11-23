#!/usr/bin/env bash
# Поднимает n8n из compose.yaml в отдельном проекте compose, загружает каждую
# контрольную точку из seeds/ задачей seed, запускает её сценарий и сверяет
# результат с test/expected/<урок>.json. Затем проверяет выгрузку и загрузку
# и сносит контейнер вместе с данными. Своих данных студента не касается.
set -euo pipefail

cd "$(dirname "$0")/.."

project=n8n-example-test
compose=(docker compose --project-name "$project")
export N8N_EXAMPLE_PROJECT="$project"

tmp=$(mktemp -d)
cleanup() {
  "${compose[@]}" down --volumes >/dev/null 2>&1 || true
  rm -rf "$tmp"
}
trap cleanup EXIT

echo "== версия n8n одна в compose.yaml и deploy/cloud-init.yaml"
local_image=$(grep -oE 'image: n8nio/n8n:[0-9.]+' compose.yaml)
cloud_image=$(grep -oE 'image: n8nio/n8n:[0-9.]+' deploy/cloud-init.yaml)
if [ "$local_image" != "$cloud_image" ]; then
  echo "версии расходятся: compose.yaml $local_image, cloud-init.yaml $cloud_image" >&2
  exit 1
fi
echo "$local_image"

echo "== запуск"
"${compose[@]}" up --detach --wait

for dir in seeds/*/; do
  lesson=$(basename "$dir")
  expected="test/expected/$lesson.json"
  echo "== контрольная точка $lesson"
  if [ ! -f "$expected" ]; then
    echo "нет ожидания $expected" >&2
    exit 1
  fi
  LESSON="$lesson" mise run seed
  workflow=$(node -e 'console.log(JSON.parse(require("fs").readFileSync(process.argv[1])).workflow)' "$expected")
  # Сервер уже держит порт брокера задач, поэтому разовый запуск берёт другой.
  "${compose[@]}" exec -T -e N8N_RUNNERS_BROKER_PORT=5690 n8n \
    n8n execute --id="$workflow" --rawOutput 2>/dev/null \
    | node test/check-output.mjs "$expected"
done

echo "== выгрузка задачей export"
N8N_EXAMPLE_DIR="$tmp/workflows" mise run export
if [ -z "$(ls "$tmp/workflows")" ]; then
  echo "выгрузка пустая" >&2
  exit 1
fi

echo "== загрузка задачей import"
N8N_EXAMPLE_DIR="$tmp/workflows" mise run import
echo "выгрузка и загрузка прошли"
