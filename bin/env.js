'use strict';
// Minimal .env loader shared by pg.js and pg-daemon.js. Deliberately doesn't
// pull in the `dotenv` package as a dependency just for this.
const fs = require('fs');
const path = require('path');

module.exports = function loadEnv() {
  const envPath = path.resolve(__dirname, '..', '.env');
  if (!fs.existsSync(envPath)) return;

  for (const rawLine of fs.readFileSync(envPath, 'utf8').split('\n')) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) continue;

    const eq = line.indexOf('=');
    if (eq === -1) continue;

    const key = line.slice(0, eq).trim();
    let value = line.slice(eq + 1).trim();
    const quoted =
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"));
    if (quoted) value = value.slice(1, -1);

    if (process.env[key] === undefined) process.env[key] = value;
  }
};
