'use strict';
// Long-running process that owns the embedded Postgres child process.
// Launched detached by `bin/pg.js up` and left running; `bin/pg.js down`
// asks it to stop by dropping a marker file, since Windows doesn't deliver
// POSIX signals the way a cross-platform stop handshake would need.
const fs = require('fs');
const EmbeddedPostgres = require('embedded-postgres');
const { Client } = require('pg');

const {
  DATA_DIR,
  LOG_FILE,
  PID_FILE,
  STOP_FILE,
  SEEDED_FILE,
  SEED_SQL,
  ROOT,
  PORT,
  DATABASE,
  USER,
  PASSWORD,
} = require('./pg-config');

const path = require('path');

fs.mkdirSync(DATA_DIR, { recursive: true });
if (fs.existsSync(STOP_FILE)) fs.unlinkSync(STOP_FILE);

function log(msg) {
  const line = `${new Date().toISOString()} ${msg}\n`;
  fs.appendFileSync(LOG_FILE, line);
}

const pg = new EmbeddedPostgres({
  databaseDir: DATA_DIR,
  user: USER,
  password: PASSWORD,
  port: PORT,
  persistent: true,
  onLog: (m) => fs.appendFileSync(LOG_FILE, m),
  onError: (m) => fs.appendFileSync(LOG_FILE, m),
});

async function main() {
  const firstRun = !fs.existsSync(SEEDED_FILE);

  if (firstRun) {
    log('Initialising new Postgres cluster (first run)...');
    await pg.initialise();
  }

  await pg.start();
  log(`Postgres ready on port ${PORT}`);

  if (firstRun) {
    await pg.createDatabase(DATABASE);
    const client = new Client({
      host: '127.0.0.1',
      port: PORT,
      user: USER,
      password: PASSWORD,
      database: DATABASE,
    });
    await client.connect();
    const seedSql = fs.readFileSync(SEED_SQL, 'utf8');
    await client.query(seedSql);
    await client.end();
    fs.writeFileSync(SEEDED_FILE, new Date().toISOString());
    log(`Seeded database "${DATABASE}" from ${path.relative(ROOT, SEED_SQL)}`);
  }

  fs.writeFileSync(PID_FILE, String(process.pid));

  const poll = setInterval(async () => {
    if (!fs.existsSync(STOP_FILE)) return;
    clearInterval(poll);
    log('Stop requested, shutting down...');
    try {
      await pg.stop();
    } catch (err) {
      log(`Error during stop: ${err.stack || err}`);
    }
    try {
      fs.unlinkSync(STOP_FILE);
    } catch {
      /* already gone */
    }
    try {
      fs.unlinkSync(PID_FILE);
    } catch {
      /* already gone */
    }
    log('Stopped.');
    process.exit(0);
  }, 500);
}

main().catch((err) => {
  log(`FATAL: ${err.stack || err}`);
  try {
    fs.unlinkSync(PID_FILE);
  } catch {
    /* not written yet */
  }
  process.exit(1);
});
