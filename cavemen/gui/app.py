"""GUI entry point and main loop (pygame window).

States: "menu" -> choose a world slot; "setup" -> manually enter the tribe
members (name, gender, age, individual prompt) for new/overwrite slots;
"sim" -> run the simulation at the configured tick rate, rendered via renderer
plus HUD overlay. ESC quits / returns to the menu in setup; F5 saves the current
world to its slot (autosave every N ticks as well); E opens a modal live prompt
editor that pauses the sim while open and writes directly into agent prompts;
"config" -> global settings overlay opened from the main menu (validated, in-place save to config.yaml).
All user-facing errors are
friendly one-liners, never stack traces.
"""
import pygame
from . import hud, renderer
from .config_editor import ConfigEditor
from .menu import MenuState
from .prompt_editor import PromptEditor
from .setup import WorldSetup
from ..config import Config, update_config_values
from ..simulation.game_loop import Simulation
from ..world import save_load


def _start_simulation(cfg, kind: str, slot, roster=None, llm_debug=False) -> tuple:
    """Create a Simulation for the menu action (new/overwrite/load).

    A non-empty `roster` spawns the manually entered tribe members instead of
    the legacy auto-generated tribe (backwards compatible default: None).
    `llm_debug` is forwarded from the --debug-llm CLI flag.
    """
    llm_enabled = bool(cfg.get("gui.sim.llm", True))
    if kind == "load":
        world = save_load.load_world(cfg, slot)
        sim = Simulation(cfg, world=world, llm_enabled=llm_enabled, llm_debug=llm_debug)
        return sim, slot
    # new or explicit overwrite: fresh world written into the chosen slot
    sim = Simulation.new_world(cfg, slot=slot, name=f"world_{slot}",
                               llm_enabled=llm_enabled, llm_debug=llm_debug, roster=roster)
    save_load.save_world(sim.world, cfg, slot, force=(kind == "overwrite"))
    return sim, slot


def run(cfg, llm_debug: bool = False) -> None:
    pygame.init()
    win_w = int(cfg.get("GUI.window_w", 1120))
    win_h = int(cfg.get("GUI.window_h", 640))
    screen = pygame.display.set_mode((win_w, win_h))
    pygame.display.set_caption("Cavemen")
    tile_px = int(cfg.get("GUI.tile_px", 16))
    tick_rate_hz = max(0.25, float(cfg.get("simulation.tick_rate_hz", 5)))
    autosave_ticks = max(1, int(cfg.get("gui.sim.autosave_ticks", 200)))
    font_title = pygame.font.Font(None, 40)
    font_item = pygame.font.Font(None, 20)
    font_bubble = pygame.font.Font(None, 14)   # speech bubbles above speaking agents

    state = "menu"
    menu_state = MenuState(cfg)
    setup_state: WorldSetup | None = None   # active only in the "setup" state
    sim: Simulation | None = None
    slot: int | None = None
    selected_uid: int | None = None
    editor: PromptEditor | None = None   # modal live prompt editor (sim paused while open)
    cfg_editor: ConfigEditor | None = None   # modal global settings overlay (opened from the main menu)
    clock = pygame.time.Clock()
    tick_acc = 0.0

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if state == "menu":
                action = menu_state.handle_event(event)
                if not action:
                    continue
                kind, slot_val = action["kind"], action.get("slot")
                if kind == "quit":
                    return
                if kind in ("new", "overwrite"):
                    # manual tribe setup before the simulation starts (Phase 9);
                    # a plain "load" goes straight into the existing world.
                    sim, slot, selected_uid = None, None, None
                    setup_state = WorldSetup(cfg, slot_val, kind=kind)
                    state = "setup"
                elif kind == "config":   # global settings overlay; no world is touched
                    cfg_editor = ConfigEditor(cfg)
                    state = "config"
                else:   # kind == "load"
                    try:
                        sim, slot = _start_simulation(cfg, kind, slot_val, llm_debug=llm_debug)
                        selected_uid = next((a.uid for a in sim.world.agents if a.alive), None)
                        state = "sim"
                    except Exception as exc:  # friendly feedback instead of traceback
                        print(f"Welt konnte nicht gestartet werden: {exc}")
            elif state == "config":
                action = cfg_editor.handle_event(event)
                if not action:
                    continue
                if action["kind"] == "cancel":   # abort without saving anything
                    cfg_editor, state = None, "menu"
                    menu_state._rebuild()        # refresh slot list on re-entry
                else:   # validated save -> persist in place (comments survive) and apply live
                    try:
                        update_config_values(action["path"], action["updates"])
                        new_cfg = Config(path=action["path"])   # reload so edits take effect now
                        cfg, menu_state.cfg, cfg_editor = new_cfg, new_cfg, None
                        menu_state._rebuild()   # worlds.max_worlds may have changed -> refresh slots
                        state = "menu"
                    except Exception as exc:    # stay open with a friendly error for the fix
                        cfg_editor.error = f"Speichern fehlgeschlagen: {exc}"
            elif state == "setup":
                result = setup_state.handle_event(event)
                if not result:
                    continue
                if result["kind"] == "cancel":   # back to the menu
                    setup_state = None
                    menu_state._rebuild()        # refresh slot list on re-entry
                    state = "menu"
                else:
                    try:
                        sim, slot = _start_simulation(cfg, result["kind"], result["slot"],
                                                     roster=result["roster"], llm_debug=llm_debug)
                        selected_uid = next((a.uid for a in sim.world.agents if a.alive), None)
                        state = "sim"
                    except Exception as exc:     # friendly feedback instead of traceback
                        print(f"Welt konnte nicht gestartet werden: {exc}")
            else:   # state == "sim"
                if editor is not None:   # modal prompt editor: sim paused, keys routed there
                    action = editor.handle_event(event)
                    if action and action.get("kind") == "close":
                        editor = None     # resume the simulation below
                        tick_acc = 0.0    # no burst of caught-up ticks on close
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_e:
                    editor = PromptEditor(sim.world, cfg)   # live prompt editing (INSTRUCTIONS §3)
                    tick_acc = 0.0       # pause the ticking while the editor is open
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    return
                if event.type == pygame.KEYDOWN and event.key == pygame.K_f and editor is None:
                    try:   # manual save (F5)
                        path = save_load.save_world(sim.world, cfg, slot, force=True)
                        print(f"Gespeichert unter {path}")
                    except save_load.SaveError as exc:
                        print(str(exc))
        tick_acc += clock.tick() / 1000.0
        if state == "sim" and editor is None:    # paused while the prompt editor is open
            while tick_acc >= 1.0 / tick_rate_hz:   # pace simulation ticks
                sim.tick()
                tick_acc -= 1.0 / tick_rate_hz
                if sim.world.tick % autosave_ticks == 0 and slot is not None:
                    try:      # periodic silent autosave into the owned slot
                        save_load.save_world(sim.world, cfg, slot, force=True)
                    except save_load.SaveError:
                        pass   # a failed autosave must never stop the game loop
            if selected_uid is None or next(
                    (a.uid for a in sim.world.agents if a.alive), None) != selected_uid:
                selected_uid = next((a.uid for a in sim.world.agents if a.alive), None)
            renderer.draw_world(screen, sim.world, win_h, tile_px, font=font_bubble)
            hud.draw_top_bar(screen, sim.world, font_item)
            hud.draw_panel(screen, sim.world, selected_uid, font_item)
        else:
            tick_acc = 0.0   # menu/setup screens do not advance the simulation
        if state == "setup":
            setup_state.draw(screen, font_title, font_item)
        elif state == "menu":
            menu_state.draw(screen, font_title, font_item)
        elif state == "config":      # settings overlay on top of the frozen menu frame
            menu_state.draw(screen, font_title, font_item)
            cfg_editor.draw(screen, font_title, font_item)
        if editor is not None:       # modal overlay on top of the frozen sim frame
            editor.draw(screen, font_title, font_item)
        pygame.display.flip()
