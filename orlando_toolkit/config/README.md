# orlando_toolkit.config

Loading YAML-based settings + user overrides.

📖 **[← Back to Architecture Overview](../../docs/architecture_overview.md)**

Use `ConfigManager()` and call:
```python
cfg = ConfigManager()
style_map = cfg.get_style_map()
```

If PyYAML is not available the code falls back to built-in defaults, ensuring the application still runs. 