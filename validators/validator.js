const fs = require('fs');
const path = require('path');
const Ajv = require('ajv');
const ajv = new Ajv({allErrors: true, verbose: true});

const schema = {
  type: "object",
  required: ["identity", "meta", "resonance", "health"],
  properties: {
    identity: { type: "object", required: ["version", "name"] },
    meta: { type: "object" },
    resonance: { type: "object" },
    health: { type: "object" }
  }
};

console.log(" Запуск Node.js-валидатора Мандалы (исправленная версия)...\n");

let errors = 0;
let checked = 0;

function scan(dir) {
  const items = fs.readdirSync(dir);

  items.forEach(item => {
    const fullPath = path.join(dir, item);

    // Пропускаем backup-папки
    if (item.toLowerCase().includes('backup') || item.toLowerCase().includes('backups')) {
      return;
    }

    if (fs.statSync(fullPath).isDirectory()) {
      const indexPath = path.join(fullPath, 'index.json');
      if (fs.existsSync(indexPath)) {
        checked++;
        try {
          const content = JSON.parse(fs.readFileSync(indexPath, 'utf8'));
          const valid = ajv.validate(schema, content);

          if (valid) {
            console.log(` ${item}  OK`);
          } else {
            console.log(` ${item}  ошибка валидации`);
            console.log("   " + ajv.errorsText());
            errors++;
          }
        } catch (e) {
          console.log(` ${item}  JSON parse error: ${e.message}`);
          errors++;
        }
      }
      scan(fullPath); // рекурсия в подпапки
    }
  });
}

const honeycombsDir = path.join(__dirname, '../honeycombs');
scan(honeycombsDir);

console.log(`\n Проверка завершена. Проверено: ${checked} сот`);
if (errors === 0) {
  console.log(" Валидатор прошёл успешно  все соты корректны!");
} else {
  console.log(` Найдено ошибок: ${errors}`);
}
