// PM2 process definition for the incompetech catalogue (lab980 protocol).
//
// Started and restarted by `incompetech deploy` (bin/incompetech) — never by
// hand:
//   env -i PATH="$PATH" HOME="$HOME" [PM2_HOME=…] [TERM=…] LANG=C.UTF-8 PORT=8072 \
//       pm2 start ecosystem.config.js --only incompetech
//   (pm2_clean in bin/incompetech; every pm2 command the CLI runs goes
//   through it, including the `pm2 jlist` that spawns the daemon when it is
//   down)
//
// This app holds no secrets, but pm2 is launched scrubbed anyway: pm2 gives
// the process the environment of the command that started it, and `pm2 save`
// writes that into ~/.pm2/dump.pm2 — so whatever the root shell happened to
// hold would otherwise get an indefinite on-disk lifetime. Nothing from the
// shell reaches the process; what it reads — PORT, HOST, INCOMPETECH_DB — is
// in /var/www/incompetech/.env (gitignored, mode 600, seeded by `incompetech
// deploy`), which run.sh sources before exec'ing python. The env block below
// carries only what the process needs to come up at all when .env is absent;
// the database path is .env's alone (the app defaults to ./data/catalog.sqlite3
// under cwd, which is the same file). Values in .env override the env block.
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
        PYTHONUNBUFFERED: '1',
      },
      out_file: '/var/log/pm2/incompetech.out.log',
      error_file: '/var/log/pm2/incompetech.err.log',
      merge_logs: true,
      log_date_format: 'YYYY-MM-DDTHH:mm:ss',
      time: true,
    },
  ],
};
