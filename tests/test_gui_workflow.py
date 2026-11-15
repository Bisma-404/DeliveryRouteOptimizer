"""Automated Verification of GUI Startup & Autocomplete / Routing Workflow."""

import os
import sys
import time
import tkinter as tk

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.gui.app import DeliveryRouteOptimizerApp, TILE_SERVERS, DEFAULT_TILE

def test_gui_full_flow():
    print("Initializing Tk root...")
    root = tk.Tk()
    root.withdraw()  # headless / hidden window
    app = DeliveryRouteOptimizerApp(root)

    # 1. Check initial empty state
    assert app.depot_stop is None, "Depot should be None at launch"
    assert len(app.customer_deliveries) == 0, "Customer deliveries should be empty at launch"
    assert app.btn_optimize["state"] == tk.DISABLED, "Optimize button should be disabled initially"
    print("PASS: App launches with empty route.")

    # 2. Check default tile server
    assert DEFAULT_TILE == "Google Maps (Standard)"
    print("PASS: Tile server defaults to Google Maps (prevents 403 OSM blocks).")

    # 3. Simulate background graph load
    print("Waiting for Karachi road network to initialize...")
    for _ in range(50):
        root.update()
        if app.geocoder is not None and app.astar_planner is not None:
            break
        time.sleep(0.1)

    assert app.geocoder is not None, "Geocoder must be initialized"
    assert app.astar_planner is not None, "AStarPlanner must be initialized"
    print("PASS: Road network and planners initialized.")

    # 4. Test Autocomplete Search for 'FAST'
    print("Testing autocomplete search for 'FAST'...")
    results = app.geocoder.search_places("FAST", limit=5)
    assert len(results) > 0, "Should find FAST locations"
    print(f"PASS: Found {len(results)} matches for 'FAST': {[r['name'] for r in results]}")

    # 5. Test Autocomplete Search for 'DHA'
    print("Testing autocomplete search for 'DHA'...")
    dha_results = app.geocoder.search_places("DHA", limit=5)
    assert len(dha_results) > 0, "Should find DHA locations"
    print(f"PASS: Found {len(dha_results)} matches for 'DHA': {[r['name'] for r in dha_results]}")

    # 6. Simulate setting FAST as Depot
    app.preview_location = results[0]
    app._on_confirm_set_depot()
    assert app.depot_stop is not None
    assert "FAST" in app.depot_stop["name"]
    assert app.btn_optimize["state"] == tk.DISABLED, "Still disabled without deliveries"
    print("PASS: FAST successfully set as depot.")

    # 7. Simulate adding DHA as Customer Delivery
    app.preview_location = dha_results[0]
    app.cust_name_var.set("Customer - DHA Phase 1")
    app.cust_priority_var.set("Normal")
    app.cust_weight_var.set(8.5)
    app._on_confirm_add_stop()
    assert len(app.customer_deliveries) == 1
    assert app.btn_optimize["state"] == tk.NORMAL, "Should be enabled with depot + 1 delivery"
    print("PASS: DHA successfully added as delivery stop. Optimize button is now ENABLED.")

    # 8. Add a second customer stop: Clifton
    clifton_results = app.geocoder.search_places("Clifton", limit=3)
    assert len(clifton_results) > 0
    app.preview_location = clifton_results[0]
    app.cust_name_var.set("Customer - Clifton")
    app.cust_priority_var.set("Urgent")
    app.cust_weight_var.set(12.0)
    app._on_confirm_add_stop()
    assert len(app.customer_deliveries) == 2
    print("PASS: Clifton added as urgent delivery stop (total 2 deliveries).")

    # 9. Test Route Optimization from UI
    print("Triggering Route Optimization via UI...")
    app._on_optimize_route_clicked()

    # Poll UI queue until optimization worker finishes and UI is updated
    for _ in range(120):
        root.update()
        app._poll_ui_queue()
        if app.btn_optimize["state"] == tk.NORMAL and app.optimized_tour is not None:
            break
        time.sleep(0.1)

    assert app.optimized_tour is not None, "Optimized tour should not be None"
    assert app.optimized_cost_km > 0.0, "Cost should be positive"
    assert len(app.route_coords) > 0, "Route coordinates should be computed"
    assert app.results_card_wrapper.winfo_manager() != "", "Results card must be displayed"
    print(f"PASS: Route optimized successfully: {app.optimized_cost_km:.2f} km with {len(app.route_coords)} road points.")

    # 10. Test Save to SQLite History
    print("Testing Save Route to SQLite...")
    initial_count = len(app.db.get_all_routes())
    import tkinter.messagebox
    tkinter.messagebox.showinfo = lambda title, message: None  # mock popup
    app._on_save_route_to_sqlite()
    new_count = len(app.db.get_all_routes())
    assert new_count == initial_count + 1, "Route count in SQLite should increase by 1"
    print(f"PASS: Route successfully saved to SQLite history (Total saved trips: {new_count}).")

    # 11. Clean up
    root.destroy()
    print("ALL GUI WORKFLOW VERIFICATIONS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_gui_full_flow()
