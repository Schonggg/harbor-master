def advise_action(level: str) -> str:
    return {"clear": "放行", "hold": "扣单"}.get(level, "引航")
