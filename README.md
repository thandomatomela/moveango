# Moveango Internal Quote Tool v18

## v18 fix

Fixes Docker Compose volume error:

```text
service "moveango-api" refers to undefined volume moveango_data
```

Persistent volumes are now correctly defined:

```yaml
volumes:
  moveango_data:
  moveango_quotes:
```

## Run

```bash
docker compose down
docker compose build --no-cache
docker compose up
```

Database persists in:

```text
moveango_data:/app/data
```

Generated PDFs persist in:

```text
moveango_quotes:/app/generated_quotes
```
