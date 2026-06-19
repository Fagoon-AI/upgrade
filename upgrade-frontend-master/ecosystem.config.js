module.exports = {
  apps: [
    {
      name: "upgrade-fe",
      cwd: "/var/www/upgrade-frontend",
      script: "node_modules/.bin/next",
      args: "start",
      env: {
        PORT: 3005,
        NODE_ENV: "production",
      },
    },
  ],
};
