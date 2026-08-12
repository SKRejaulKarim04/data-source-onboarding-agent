#!/usr/bin/env node
'use strict';
// Replaces `docker compose up/down/logs/exec postgres psql` with a Postgres
// instance run as a plain local process (no Docker daemon required), via the
// `embedded-postgres` package. See bin/pg-daemon.js for the process that
// actually owns Postgres.
const fs = require('fs');
const net = require('net');
const path = require('path');
const { spawn, spawnSync } = require('child_process');

const { DATA_DIR, LOG_FILE, PID_FILE, STOP_FILE, PORT, DATABASE, USER, PASSWORD } = require('./pg-config');

function isRunning() {
  if (!fs.existsSync(PID_FILE)) return false;
  const pid = Number(fs.readFileSync(PID_FILE, 'utf8').trim());
  if (!pid) return false;
  try {
    process.kill(pid, 0); // liveness probe: sends nothing, just checks existence
    return pid;
  } catch {
    return false;
  }
}

function waitForPort(port, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve, reject) => {
    (function attempt() {
      const socket = net.connect(port, '127.0.0.1');
      socket.once('connect', () => {
        socket.destroy();
        resolve();
      });
      socket.once('error', () => {
        socket.destroy();
        if (Date.now() > deadline) reject(new Error('Timed out waiting for Postgres to become ready'));
        else setTimeout(attempt, 300);
      });
    })();
  });
}

async function up() {
  const pid = isRunning();
  if (pid) {
    console.log(`Postgres already running (pid ${pid}) on port ${PORT}`);
    return;
  }
  fs.mkdirSync(DATA_DIR, { recursive: true });

  const child = spawn(process.execPath, [path.join(__dirname, 'pg-daemon.js')], {
    detached: true,
    stdio: 'ignore',
    windowsHide: true,
  });
  child.unref();

  console.log('Waiting for Postgres...');
  await waitForPort(PORT, 30000);

  // A port that answers is not proof that *our* daemon answered it. A Docker
  // container or a system Postgres on the same port looks identical from here,
  // and reporting "Ready" in that case sends you off debugging the wrong
  // database. Wait for the daemon to claim the pid file before believing it.
  const started = await waitForDaemon(10000);
  if (started) {
    console.log(`Ready on localhost:${PORT} (pid ${started})`);
    return;
  }

  console.error(
    `\nPort ${PORT} is answering, but the embedded daemon did not start.\n` +
      `Something else is already listening there — check \`docker ps\` — or read\n` +
      `${LOG_FILE} for why the daemon exited.`
  );
  process.exitCode = 1;
}

function waitForDaemon(timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve) => {
    (function attempt() {
      const pid = isRunning();
      if (pid) return resolve(pid);
      if (Date.now() > deadline) return resolve(false);
      setTimeout(attempt, 250);
    })();
  });
}

async function down() {
  if (!isRunning()) {
    console.log('Postgres is not running.');
    return;
  }
  fs.writeFileSync(STOP_FILE, 'stop');

  const deadline = Date.now() + 15000;
  while (isRunning() && Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 300));
  }
  console.log(isRunning() ? 'Timed out waiting for shutdown.' : 'Stopped (data kept).');
}

async function reset() {
  await down();
  fs.rmSync(DATA_DIR, { recursive: true, force: true });
  console.log('Data directory wiped. Next `up` will re-initialise and reseed.');
}

async function status() {
  const pid = isRunning();
  console.log(
    pid
      ? `Running (pid ${pid}) — postgres://${USER}:***@localhost:${PORT}/${DATABASE}`
      : 'Not running.'
  );
}

function logs() {
  if (!fs.existsSync(LOG_FILE)) {
    console.log('No log file yet — run `npm run up` first.');
    return;
  }
  process.stdout.write(fs.readFileSync(LOG_FILE, 'utf8'));

  let position = fs.statSync(LOG_FILE).size;
  console.log('--- tailing (Ctrl+C to stop) ---');
  fs.watchFile(LOG_FILE, { interval: 500 }, () => {
    const { size } = fs.statSync(LOG_FILE);
    if (size < position) position = 0; // file was truncated/replaced
    if (size > position) {
      const stream = fs.createReadStream(LOG_FILE, { start: position, end: size - 1 });
      stream.pipe(process.stdout);
      position = size;
    }
  });
}

async function psql() {
  if (!isRunning()) {
    console.error('Postgres is not running. Run `npm run up` first.');
    process.exitCode = 1;
    return;
  }

  const hasRealPsql = spawnSync('psql', ['--version'], { stdio: 'ignore' }).error === undefined;
  if (hasRealPsql) {
    const result = spawnSync(
      'psql',
      ['-h', '127.0.0.1', '-p', String(PORT), '-U', USER, '-d', DATABASE],
      { stdio: 'inherit', env: { ...process.env, PGPASSWORD: PASSWORD } }
    );
    process.exitCode = result.status ?? 0;
    return;
  }

  console.log('No system `psql` on PATH — dropping into a minimal SQL shell instead.');
  await miniRepl();
}

async function miniRepl() {
  const { Client } = require('pg');
  const readline = require('readline');

  const client = new Client({ host: '127.0.0.1', port: PORT, user: USER, password: PASSWORD, database: DATABASE });
  await client.connect();
  console.log(`Connected to "${DATABASE}" as "${USER}". End statements with ";". \\q to quit.`);

  const rl = readline.createInterface({ input: process.stdin, output: process.stdout, prompt: `${DATABASE}=> ` });
  let buffer = '';
  rl.prompt();

  rl.on('line', async (line) => {
    if (line.trim() === '\\q') {
      rl.close();
      return;
    }
    buffer += `${line}\n`;
    if (buffer.trim().endsWith(';')) {
      const statement = buffer;
      buffer = '';
      try {
        const res = await client.query(statement);
        if (res.rows && res.rows.length) console.table(res.rows);
        console.log(`(${res.rowCount ?? 0} row${res.rowCount === 1 ? '' : 's'})`);
      } catch (err) {
        console.error(err.message);
      }
      rl.setPrompt(`${DATABASE}=> `);
    } else {
      rl.setPrompt(`${DATABASE}-> `);
    }
    rl.prompt();
  });

  rl.on('close', async () => {
    await client.end();
    process.exit(0);
  });
}

const commands = { up, down, reset, status, logs, psql };
const cmd = process.argv[2];

if (!commands[cmd]) {
  console.error(`Usage: node bin/pg.js <${Object.keys(commands).join('|')}>`);
  process.exit(1);
}

Promise.resolve(commands[cmd]()).catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
