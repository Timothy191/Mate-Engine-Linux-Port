// pm2 process definitions for the MateEngine agent stack.
// Start / reload with:  pm2 startOrReload ecosystem.config.js
const fs = require("fs");
const path = require("path");

const venvPython = path.join(__dirname, ".venv", "bin", "python");
const pythonInterpreter = fs.existsSync(venvPython) ? venvPython : "python3";

module.exports = {
  apps: [
    {
      name: "mate-bridge",
      script: "mate_bridge.py",
      interpreter: pythonInterpreter,
      cwd: __dirname,
      max_restarts: 10,
      min_uptime: "10s",
      restart_delay: 2000,
      out_file: "logs/mate-bridge.out.log",
      error_file: "logs/mate-bridge.err.log",
      merge_logs: true,
      time: true,
    },
    {
      name: "mate-ambient",
      script: "scripts/desktop_ambient_daemon.py",
      interpreter: "python3",
      cwd: __dirname,
      max_restarts: 10,
      min_uptime: "10s",
      restart_delay: 2000,
      out_file: "logs/mate-ambient.out.log",
      error_file: "logs/mate-ambient.err.log",
      merge_logs: true,
      time: true,
    },
  ],
};
