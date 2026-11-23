// Сверяет вывод `n8n execute --rawOutput` с ожиданием из test/expected/<урок>.json.
// Ожидание задаёт ноду и поля её первой записи, лишние поля в выводе допустимы.
//
//   node test/check-output.mjs <expected.json> < output
import { readFileSync } from "node:fs";

const expected = JSON.parse(readFileSync(process.argv[2], "utf8"));
const raw = readFileSync(0, "utf8");
const execution = JSON.parse(raw.slice(raw.indexOf("{"), raw.lastIndexOf("}") + 1));

const fail = (message) => {
  console.error(message);
  process.exit(1);
};

if (execution.status !== "success") {
  fail(`запуск закончился со статусом ${execution.status}`);
}

const runs = execution.data?.resultData?.runData?.[expected.node];
if (!runs) {
  fail(`нода «${expected.node}» не выполнялась`);
}

const json = runs.at(-1)?.data?.main?.[0]?.[0]?.json ?? {};
for (const [key, value] of Object.entries(expected.json)) {
  if (json[key] !== value) {
    fail(`нода «${expected.node}»: ${key} = ${JSON.stringify(json[key])}, ожидалось ${JSON.stringify(value)}`);
  }
}
console.log(`нода «${expected.node}» отдала ожидаемое`);
