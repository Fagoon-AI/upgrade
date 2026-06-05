module.exports = {
    apps: [
        {
            name: "prod-agent-workflow",
            script: "./scripts/run.sh",
            exec_mode: "fork",
            instances: 1,
            wait_ready: true,
            autorestart: false,
            max_restarts: 5,
            env: {
                APP_ENV: "PROD"
            }
        },
        {
            name: "dev-agent-workflow",
            script: "./scripts/run.sh",
            exec_mode: "fork",
            instances: 1,
            wait_ready: true,
            autorestart: false,
            max_restarts: 5,
            env: {
                APP_ENV: "DEV"
            }
        }
    ]
}
