"""Flask blueprints for the Novelforge web demo.

Each module registers a Blueprint named after its top-level concern
(presets / projects / env / runner / novels). web.app imports and
registers all of them; no blueprint imports another blueprint.
"""
