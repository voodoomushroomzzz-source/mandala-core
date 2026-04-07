const fs = require('fs');
const path = require('path');
const Ajv = require('ajv');
const ajv = new Ajv({allErrors: true});

const schema = {
  type: "object",
  required: ["identity", "meta", "resonance", "health"],
  properties: {
    identity: { type: "object", required: ["version"] },
    meta: { type: "object" },
    resonance: { type: "object" },
    health: { type: "object" }
  }
};

const validateAll = () => {
  const honeycombsDir = path.join(__dirname, '../honeycombs');
  let errors = 0;

  function scan(dir) {
    fs.readdirSync(dir).forEach(file => {
      const fullPath = path.join(dir, file);
      if (fs.statSync(fullPath).isDirectory()) {
        if (fs.existsSync(path.join(fullPath, 'index.json'))) {
          try {
            const content = JSON.parse(fs.readFileSync(path.join(fullPath, 'index.json'), 'utf8'));
            const valid = ajv.validate(schema, content);
            if (!valid) {
              console.error(` ${file}:`, ajv.errorsText());
              errors++;
            } else {
              console.log(` ${file}  OK`);
            }
          } catch (e) {
            console.error(` ${file}: JSON error`);
            errors++;
          }
        }
        scan(fullPath);
      }
    });
  }

  scan(honeycombsDir);
  return errors === 0;
};

if (require.main === module) {
  console.log(" Запуск Node.js валидатора Мандалы...");
  const success = validateAll();
  process.exit(success ? 0 : 1);
}
