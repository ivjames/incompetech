// PM2 process definition for the incompetech catalogue (lab980 protocol).
//
// Started and restarted by `incompetech deploy` (bin/incompetech) — never by
// hand:  pm2 start ecosystem.config.js --only incompetech
//
// There is no key block and nothing to unset before launching: this app holds
// no secrets. What it reads is PORT, HOST and INCOMPETECH_DB, all of which
// live in /var/www/incompetech/.env (gitignored) and reach the process through
// run.sh, which sources that file before exec'ing python. Values in .env
// override the env block below.
module.exports = {
  apps: [
    {
      name: 'incompetech',
      cwd: '/var/www/incompetech',     // <-- absolute path to the checkout
      script: './run.sh',              // sources ./.env, execs `python -m web.app`
      interpreter: '/bin/sh',
      instances: 1,                    // fork mode; see exec_mode below
      // Explicit, and it matters: setting `instances` alone flips pm2 into
      // cluster mode, whose startup crashes land in ~/.pm2/pm2.log rather than
      // this app's own error log. Every site on this box runs fork.
      exec_mode: 'fork',
      autorestart: true,
      max_restarts: 10,
      restart_delay: 4000,
      max_memory_restart: '300M',
      kill_timeout: 5000,
      env: {
        PORT: '8072',
        HOST: '127.0.0.1',
        INCOMPETECH_DB: '/var/www/incompetech/data/catalog.sqlite3',
        PYTHONUNBUFFERED: '1',
      },
      out_file: '/var/log/pm2/incompetech.out.log',
      error_file: '/var/log/pm2/incompetech.err.log',
      merge_logs: true,
      time: true,
    },
  ],
};
