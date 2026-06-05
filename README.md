# agents-workflow

## Run Server
```bash
chmod +x scripts/*
```

```bash
./scripts/run.sh
```

### Running Application for Development Environment
```bash
pm2 start ecosystem.config.js --only dev-agent-workflow
```

### Running Application for Production Environment
```bash
pm2 start ecosystem.config.js --only prod-agent-workflow
```
