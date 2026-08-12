'use strict';
// Shared config + paths for pg.js and pg-daemon.js.
const path = require('path');
require('./env')();

const ROOT = path.resolve(__dirname, '..');
const DATA_DIR = path.join(ROOT, '.pgdata');

module.exports = {
  ROOT,
  DATA_DIR,
  // Deliberately NOT inside DATA_DIR: initdb refuses to initialise a cluster in
  // a directory that already has anything in it, and the daemon logs its first
  // line before it calls initdb. A log file there breaks every first run.
  LOG_FILE: path.join(ROOT, '.pgdata.log'),
  PID_FILE: path.join(DATA_DIR, 'pg.pid'),
  STOP_FILE: path.join(DATA_DIR, 'stop.request'),
  SEEDED_FILE: path.join(DATA_DIR, '.seeded'),
  SEED_SQL: path.join(ROOT, 'docker', 'postgres', '01_seed.sql'),
  PORT: Number(process.env.DSOA_PG_PORT || 55432),
  DATABASE: process.env.DSOA_PG_DATABASE || 'dsoa_source',
  USER: process.env.DSOA_PG_USERNAME || 'dsoa',
  PASSWORD: process.env.DSOA_PG_PASSWORD || 'dsoa_local_dev',
};
