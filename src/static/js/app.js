(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const tileUrls = {
    "Google Maps (Standard)": "https://mt0.google.com/vt/lyrs=m&hl=en&x={x}&y={y}&z={z}&s=Ga",
    Voyager: "https://a.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png",
    "Positron (Light)": "https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
    "Dark Matter": "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png"
  };
  const pageTitles = {
    dashboard: "Overview",
    planner: "Route planner",
    results: "Route results",
    history: "Trip history",
    analytics: "Analytics",
    settings: "Fleet settings"
  };
  const charts = {};
  let state = null;
  let selectedPlace = null;
  let editingDeliveryIndex = null;
  let searchTimer = null;
  let toastTimer = null;
  let historyRows = [];
  let maps = {};
  let mapLayers = {};
  let markers = { planner: [], results: [] };
  let zoneLayers = { planner: [], results: [] };
  let analyticsData = null;
  let analyticsZones = null;
  let zoneData = null;
  const simulation = { arrived: false, paused: false, coordinates: [], waypoint: 0, target: 0, timer: null, marker: null };

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[char]));
  }

  async function api(url, options = {}) {
    const config = { ...options, headers: { ...(options.headers || {}) } };
    if (config.body && typeof config.body !== "string") {
      config.headers["Content-Type"] = "application/json";
      config.body = JSON.stringify(config.body);
    }
    const response = await fetch(url, config);
    const contentType = response.headers.get("content-type") || "";
    const body = contentType.includes("application/json") ? await response.json() : {};
    if (!response.ok) throw new Error(body.error || `Request failed (${response.status}).`);
    return body;
  }

  function notify(message, error = false) {
    const toast = $("#toast");
    toast.textContent = message;
    toast.classList.toggle("error", error);
    toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("show"), 3200);
  }

  function setTheme(theme) {
    const next = theme === "dark" ? "dark" : "light";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("route-desk-theme", next);
    $("#theme-toggle").textContent = next === "dark" ? "☼" : "◐";
    $("#theme-toggle").title = `Switch to ${next === "dark" ? "light" : "dark"} theme`;
    Object.values(charts).forEach((chart) => {
      if (chart) chart.destroy();
    });
    Object.keys(charts).forEach((key) => delete charts[key]);
    if (state) {
      drawConvergence(state.result);
      if (analyticsData) drawAnalyticsCharts(analyticsData, analyticsZones);
      if (zoneData) drawElbowChart(zoneData);
    }
  }

  function showView(name) {
    if (!pageTitles[name]) name = "dashboard";
    $$(".view").forEach((view) => view.classList.toggle("active", view.id === `view-${name}`));
    $$(".nav-item[data-nav]").forEach((button) => button.classList.toggle("active", button.dataset.nav === name));
    $("#page-title").textContent = pageTitles[name];
    if (name === "history") refreshHistory();
    if (name === "analytics") refreshAnalytics();
    if (name === "planner") refreshZones();
    if (name === "results") renderResults();
    setTimeout(() => {
      Object.values(maps).forEach((map) => map && map.invalidateSize());
      Object.values(charts).forEach((chart) => chart && chart.resize());
    }, 100);
  }

  function setNetwork(status, error) {
    const dot = $("#network-dot");
    dot.classList.toggle("online", status === "online");
    dot.classList.toggle("offline", status === "offline");
    $("#network-label").textContent = status === "online"
      ? "Road graph ready"
      : status === "offline" ? "Road graph unavailable" : "Connecting to road network";
    const alert = $("#graph-alert");
    if (status === "offline") {
      alert.textContent = `The local road network could not be loaded. ${error || "Check the application log and graph cache."}`;
      alert.classList.remove("hidden");
    } else {
      alert.classList.add("hidden");
    }
  }

  function updateDashboard(dashboard = {}) {
    $("#kpi-routes").textContent = dashboard.total_routes || 0;
    $("#kpi-distance").textContent = Number(dashboard.total_distance_km || 0).toFixed(1);
    $("#kpi-savings").textContent = Number(dashboard.avg_saved_pct || 0).toFixed(1);
    $("#kpi-completed").textContent = dashboard.completed_deliveries || 0;
    $("#kpi-pending").textContent = dashboard.pending_deliveries || 0;
    const recent = dashboard.recent_routes || [];
    $("#recent-routes").innerHTML = recent.length ? recent.map((route) => `
      <tr>
        <td><strong>${escapeHtml(route.route_name)}</strong><small class="table-sub">${escapeHtml(route.depot_name)}</small></td>
        <td>${Number(route.num_stops) || 0}</td>
        <td>${Number(route.total_distance_km || 0).toFixed(2)} km</td>
        <td>${Number(route.saved_pct || 0).toFixed(1)}%</td>
        <td><span class="status-pill ${statusClass(route.status)}">${escapeHtml(route.status)}</span></td>
      </tr>`).join("") : '<tr><td class="empty-cell" colspan="5">No saved routes yet.</td></tr>';
  }

  function statusClass(status) {
    return String(status || "").toLowerCase().replace(/\s+/g, "-");
  }

  function renderState(data) {
    state = data;
    if (!data.result) {
      stopVehicle();
      simulation.coordinates = [];
      simulation.waypoint = 0;
      simulation.arrived = false;
      simulation.paused = false;
    }
    setNetwork(data.graph_status, data.graph_error);
    if (data.dashboard) updateDashboard(data.dashboard);
    updateSettingsForm(data.settings);
    renderPlanner(data);
    renderResults();
  }

  async function refreshState() {
    renderState(await api("/api/state"));
  }

  function updateSettingsForm(settings) {
    if (!settings) return;
    $("#setting-capacity").value = settings.capacity_kg;
    $("#setting-speed").value = settings.speed_kmh;
    $("#setting-service").value = settings.service_mins;
    $("#setting-solver").value = settings.solver;
    $("#setting-search").value = settings.search_method;
    $("#setting-map").value = settings.map_style;
    $("#setting-round-trip").checked = settings.round_trip;
    $("#map-style").value = settings.map_style;
    setMapStyle(settings.map_style);
  }

  function renderPlanner(data) {
    const depot = data.depot;
    const deliveries = data.deliveries || [];
    const maxCapacity = Number(data.settings?.capacity_kg || 50);
    const load = deliveries.reduce((sum, stop) => sum + Number(stop.weight_kg || 0), 0);
    $("#capacity-max").textContent = maxCapacity.toFixed(0);
    $("#load-weight").textContent = load.toFixed(1);
    const percent = maxCapacity ? Math.min(100, load / maxCapacity * 100) : 0;
    const bar = $("#capacity-bar");
    bar.style.width = `${percent}%`;
    bar.classList.toggle("over", load > maxCapacity);
    $("#capacity-note").textContent = load > maxCapacity
      ? `Over capacity by ${(load - maxCapacity).toFixed(1)} kg. Reduce the load or adjust fleet settings.`
      : `${Math.max(0, maxCapacity - load).toFixed(1)} kg available`;
    $("#stop-count-label").textContent = `${deliveries.length} delivery stop${deliveries.length === 1 ? "" : "s"}${depot ? " · depot set" : " · no depot selected"}`;

    const allStops = depot ? [{ ...depot, type: "depot" }, ...deliveries] : deliveries;
    $("#stop-list").innerHTML = allStops.length ? allStops.map((stop, index) => {
      const isDepot = stop.type === "depot";
      const deliveryIndex = isDepot ? -1 : index - (depot ? 1 : 0);
      const stopNumber = isDepot ? "D" : deliveryIndex + 1;
      const details = isDepot ? "Starting depot" : `${Number(stop.weight_kg || 0).toFixed(1)} kg · ${escapeHtml(stop.time_window || "Anytime")}`;
      const priority = isDepot ? "" : `<span class="badge ${stop.priority === "Urgent" ? "urgent" : ""}">${escapeHtml(stop.priority || "Normal")}</span>`;
      return `<div class="stop-item">
        <span class="stop-number ${isDepot ? "depot" : ""}">${stopNumber}</span>
        <div><strong>${escapeHtml(stop.name)}</strong><small>${escapeHtml(stop.address || details)}</small>
          <div class="stop-meta">${!isDepot ? `${priority}<span class="badge">${details}</span>` : '<span class="badge">Depot</span>'}</div>
        </div>
        ${isDepot
          ? '<button class="stop-remove" type="button" data-action="remove-depot" title="Remove depot">×</button>'
          : `<div class="stop-actions">
              <button class="stop-edit" type="button" data-action="edit-stop" data-index="${deliveryIndex}" title="Edit stop">Edit</button>
              <button class="stop-remove" type="button" data-action="remove-stop" data-index="${deliveryIndex}" title="Remove stop">×</button>
            </div>`}
      </div>`;
    }).join("") : '<div class="empty-stops">Add a depot and delivery stops to build your route.</div>';
    $("#optimize-button").disabled = data.graph_status !== "online" || !depot || deliveries.length === 0 || load > maxCapacity;
    $("#planner-status").textContent = data.graph_status === "online"
      ? !depot ? "Select a starting depot to begin."
        : deliveries.length === 0 ? "Add at least one delivery stop."
          : load > maxCapacity ? "Cargo load exceeds the selected vehicle capacity."
            : "Ready to calculate a road-based route."
      : data.graph_status === "offline" ? "The road graph is unavailable; route calculation is disabled."
        : "Waiting for the Karachi road graph…";

    drawStopsOnMap("planner", allStops);
    renderZones(data.clusters);
  }

  function renderZones(summary) {
    const container = $("#zone-list");
    if (!summary?.clusters) {
      container.innerHTML = '<span class="muted-text">Add two or more deliveries to create zones.</span>';
      return;
    }
    container.innerHTML = Object.values(summary.clusters).map((zone) =>
      `<span class="zone-chip"><i style="background:${escapeHtml(zone.color)}"></i>${escapeHtml(zone.name)} · ${zone.count} stops · ${Number(zone.total_weight_kg || 0).toFixed(1)} kg</span>`
    ).join("");
  }

  function initMaps() {
    if (!window.L) {
      $("#planner-status").textContent = "The map library could not be loaded. Check your internet connection.";
      return;
    }
    maps.planner = L.map("route-map", { zoomControl: true }).setView([24.8607, 67.0011], 12);
    maps.results = L.map("results-map", { zoomControl: true }).setView([24.8607, 67.0011], 12);
    setMapStyle("Google Maps (Standard)");
    maps.planner.on("click", (event) => {
      const { lat, lng } = event.latlng;
      choosePlace({
        name: `Map point ${lat.toFixed(4)}, ${lng.toFixed(4)}`,
        address: `Selected from the map · ${lat.toFixed(5)}, ${lng.toFixed(5)}`,
        latitude: lat,
        longitude: lng,
        category: "Map point"
      });
    });
  }

  function setMapStyle(style) {
    if (!window.L) return;
    const attribution = style === "Google Maps (Standard)"
      ? "&copy; Google Maps"
      : '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &middot; &copy; CARTO';
    Object.keys(maps).forEach((key) => {
      if (!maps[key]) return;
      if (mapLayers[key]) maps[key].removeLayer(mapLayers[key]);
      mapLayers[key] = L.tileLayer(tileUrls[style] || tileUrls["Google Maps (Standard)"], {
        maxZoom: 19,
        attribution
      }).addTo(maps[key]);
    });
  }

  function pinIcon(kind, label, zoneColor) {
    const color = /^#[0-9a-f]{6}$/i.test(zoneColor || "") ? zoneColor : "";
    return L.divIcon({
      className: "",
      html: `<div class="map-pin ${kind}"${color ? ` style="background:${color}"` : ""}><span>${escapeHtml(label)}</span></div>`,
      iconSize: [25, 30],
      iconAnchor: [12, 29]
    });
  }

  function clearMapMarkers(key) {
    (markers[key] || []).forEach((layer) => maps[key].removeLayer(layer));
    markers[key] = [];
  }

  function clearZoneLayers(key) {
    (zoneLayers[key] || []).forEach((layer) => maps[key].removeLayer(layer));
    zoneLayers[key] = [];
  }

  function distanceMeters(lat1, lon1, lat2, lon2) {
    const radians = (degrees) => degrees * Math.PI / 180;
    const latDelta = radians(lat2 - lat1);
    const lonDelta = radians(lon2 - lon1);
    const value = Math.sin(latDelta / 2) ** 2
      + Math.cos(radians(lat1)) * Math.cos(radians(lat2)) * Math.sin(lonDelta / 2) ** 2;
    return 6371000 * 2 * Math.atan2(Math.sqrt(value), Math.sqrt(1 - value));
  }

  function drawClusterZones(key, summary, stops) {
    clearZoneLayers(key);
    if (!maps[key] || !summary?.clusters) return L.latLngBounds([]);
    const bounds = L.latLngBounds([]);
    Object.entries(summary.clusters).forEach(([clusterKey, zone]) => {
      const clusterId = Number(clusterKey);
      const members = stops.filter((stop) => Number(stop.cluster) === clusterId && stop.type !== "depot");
      if (!members.length) return;
      const centroid = summary.centroids?.[clusterId] || [
        members.reduce((sum, stop) => sum + Number(stop.latitude), 0) / members.length,
        members.reduce((sum, stop) => sum + Number(stop.longitude), 0) / members.length
      ];
      const center = [Number(centroid[0]), Number(centroid[1])];
      const spread = Math.max(...members.map((stop) =>
        distanceMeters(center[0], center[1], Number(stop.latitude), Number(stop.longitude))
      ));
      const radius = Math.max(120, spread * 1.15 + 45);
      const area = L.circle(center, {
        radius,
        color: zone.color,
        weight: 1.5,
        opacity: .8,
        fillColor: zone.color,
        fillOpacity: .11
      }).bindPopup(
        `<strong>${escapeHtml(zone.name)}</strong><br>${members.length} delivery stop${members.length === 1 ? "" : "s"} · ${Number(zone.total_weight_kg || 0).toFixed(1)} kg`
      ).addTo(maps[key]);
      const label = L.marker(center, {
        icon: L.divIcon({
          className: "",
          html: `<span class="zone-map-label" style="--zone-color:${escapeHtml(zone.color)}">${escapeHtml(zone.name)}</span>`,
          iconSize: [68, 22],
          iconAnchor: [34, 11]
        }),
        interactive: false,
        keyboard: false,
        zIndexOffset: 500
      }).addTo(maps[key]);
      zoneLayers[key].push(area, label);
      bounds.extend(area.getBounds());
    });
    return bounds;
  }

  function drawStopsOnMap(key, stops) {
    if (!maps[key]) return;
    clearMapMarkers(key);
    const zoneBounds = drawClusterZones(key, state?.clusters, stops || []);
    (stops || []).forEach((stop, index) => {
      if (!Number.isFinite(Number(stop.latitude)) || !Number.isFinite(Number(stop.longitude))) return;
      const depot = stop.type === "depot";
      const stopNumber = depot ? "D" : state?.depot ? index : index + 1;
      const icon = pinIcon(
        depot ? "depot" : stop.priority === "Urgent" ? "urgent" : "delivery",
        stopNumber,
        stop.cluster_color
      );
      const marker = L.marker([stop.latitude, stop.longitude], { icon }).bindPopup(
        `<strong>${escapeHtml(stop.name)}</strong><br>${escapeHtml(depot ? "Starting depot" : `${stop.weight_kg || 0} kg · ${stop.priority || "Normal"}`)}`
      ).addTo(maps[key]);
      markers[key].push(marker);
    });
    const points = (stops || []).filter((stop) =>
      Number.isFinite(Number(stop.latitude)) && Number.isFinite(Number(stop.longitude))
    );
    const bounds = L.latLngBounds(points.map((stop) => [stop.latitude, stop.longitude]));
    if (zoneBounds.isValid()) bounds.extend(zoneBounds);
    if (bounds.isValid()) {
      maps[key].fitBounds(bounds, { padding: [30, 30], maxZoom: 14 });
    }
  }

  function drawRouteOnMap(key, result, stops) {
    if (!maps[key]) return;
    clearMapMarkers(key);
    if (!result) {
      drawStopsOnMap(key, stops);
      return;
    }
    const zoneBounds = drawClusterZones(key, state?.clusters, stops || []);
    if (result.coordinates?.length > 1) {
      const line = L.polyline(result.coordinates, { color: "#c44f53", weight: 5, opacity: .88, lineCap: "round", lineJoin: "round" }).addTo(maps[key]);
      markers[key].push(line);
    }
    const itinerary = result.itinerary || [];
    const displayed = itinerary.filter((stop, index) => stop.type === "depot" ? index === 0 : true);
    displayed.forEach((stop, index) => {
      const depot = stop.type === "depot";
      const icon = pinIcon(depot ? "depot" : stop.priority === "Urgent" ? "urgent" : "delivery", depot ? "D" : index);
      const marker = L.marker([stop.latitude, stop.longitude], { icon }).bindPopup(
        `<strong>${escapeHtml(stop.name)}</strong><br>${escapeHtml(depot ? "Starting depot" : `Stop ${index} · ${stop.priority || "Normal"}`)}`
      ).addTo(maps[key]);
      markers[key].push(marker);
    });
    if (result.coordinates?.length > 1) {
      const bounds = L.latLngBounds(result.coordinates);
      if (zoneBounds.isValid()) bounds.extend(zoneBounds);
      maps[key].fitBounds(bounds, { padding: [30, 30], maxZoom: 15 });
    } else {
      drawStopsOnMap(key, stops);
    }
  }

  async function searchPlaces(query) {
    const resultBox = $("#search-results");
    const spinner = $("#search-spinner");
    if (!query.trim()) {
      resultBox.classList.add("hidden");
      return;
    }
    spinner.classList.remove("hidden");
    try {
      const results = await api(`/api/search?q=${encodeURIComponent(query)}`);
      resultBox.innerHTML = results.length ? results.map((place, index) => `
        <button class="search-result" type="button" data-search-index="${index}">
          <strong>${escapeHtml(place.name)}</strong>
          <small>${escapeHtml(place.address || place.category || "Karachi")}</small>
        </button>`).join("") : '<div class="search-empty">No matching Karachi locations found.</div>';
      resultBox._places = results;
      resultBox.classList.remove("hidden");
    } catch (error) {
      resultBox.innerHTML = `<div class="search-empty">${escapeHtml(error.message)}</div>`;
      resultBox.classList.remove("hidden");
    } finally {
      spinner.classList.add("hidden");
    }
  }

  function choosePlace(place) {
    selectedPlace = place;
    $("#selected-name").textContent = place.name;
    $("#selected-address").textContent = place.address || "Selected map coordinates";
    $("#selected-place").classList.remove("hidden");
    $("#search-results").classList.add("hidden");
    $("#place-search").value = place.name;
    if (maps.planner) {
      clearMapMarkers("planner");
      const marker = L.marker([place.latitude, place.longitude], { icon: pinIcon("preview", "•") }).addTo(maps.planner);
      markers.planner.push(marker);
      maps.planner.setView([place.latitude, place.longitude], 15);
    }
  }

  function clearSelection() {
    selectedPlace = null;
    $("#selected-place").classList.add("hidden");
    $("#place-search").value = "";
    $("#search-results").classList.add("hidden");
    if (state) drawStopsOnMap("planner", state.stops);
  }

  async function applyPlannerResponse(data) {
    renderState(data);
    if ($("#view-planner").classList.contains("active")) {
      setTimeout(() => maps.planner?.invalidateSize(), 50);
      await refreshZones();
    }
  }

  async function setDepot() {
    if (!selectedPlace) return;
    const data = await api("/api/depot", { method: "POST", body: { place: selectedPlace } });
    await applyPlannerResponse(data);
    clearSelection();
    notify("Starting depot set.");
  }

  function openDeliveryEditor(index = null) {
    if (Number.isInteger(index)) {
      const delivery = state?.deliveries?.[index];
      if (!delivery) return;
      clearSelection();
      editingDeliveryIndex = index;
      $("#delivery-editor-title").textContent = "Edit delivery";
      $("#confirm-delivery").textContent = "Save changes";
      $("#selected-place").classList.add("hidden");
      $("#delivery-name").value = delivery.name;
      $("#delivery-weight").value = delivery.weight_kg;
      $("#delivery-priority").value = delivery.priority || "Normal";
      $("#delivery-window").value = delivery.time_window || "Anytime";
    } else {
      if (!selectedPlace) return;
      editingDeliveryIndex = null;
      $("#delivery-editor-title").textContent = "Delivery details";
      $("#confirm-delivery").textContent = "Add to route";
      $("#delivery-name").value = selectedPlace.name;
      $("#delivery-weight").value = "5";
      $("#delivery-priority").value = "Normal";
      $("#delivery-window").value = "Anytime";
    }
    $("#delivery-editor").classList.remove("hidden");
    $("#delivery-name").focus();
  }

  async function addDelivery() {
    const details = {
      name: $("#delivery-name").value,
      weight_kg: Number($("#delivery-weight").value),
      priority: $("#delivery-priority").value,
      time_window: $("#delivery-window").value
    };
    if (editingDeliveryIndex !== null) {
      await applyPlannerResponse(await api(`/api/stops/${editingDeliveryIndex}`, {
        method: "PATCH",
        body: details
      }));
      editingDeliveryIndex = null;
      $("#delivery-editor").classList.add("hidden");
      notify("Delivery details updated.");
      return;
    }
    if (!selectedPlace) return;
    const data = await api("/api/stops", {
      method: "POST",
      body: { ...details, place: selectedPlace }
    });
    await applyPlannerResponse(data);
    $("#delivery-editor").classList.add("hidden");
    clearSelection();
    notify("Delivery added to the route.");
  }

  async function optimizeRoute() {
    const button = $("#optimize-button");
    button.disabled = true;
    button.textContent = "Calculating route…";
    $("#planner-status").textContent = "Building road distances and solving the route.";
    try {
      const data = await api("/api/optimize", { method: "POST", body: {} });
      renderState(data);
      renderResults();
      showView("results");
      notify("Route calculation completed.");
    } catch (error) {
      notify(error.message, true);
      $("#planner-status").textContent = error.message;
    } finally {
      button.textContent = "Calculate route →";
      button.disabled = !state?.depot || !(state?.deliveries || []).length || state?.graph_status !== "online";
    }
  }

  function formatDuration(minutes) {
    const total = Math.max(0, Math.round(minutes || 0));
    const hours = Math.floor(total / 60);
    return hours ? `${hours}h ${total % 60}m` : `${total} min`;
  }

  function renderResults() {
    const result = state?.result;
    $("#results-empty").classList.toggle("hidden", Boolean(result));
    $("#results-content").classList.toggle("hidden", !result);
    if (!result) return;
    $("#result-subtitle").textContent = `${result.solver_name} · ${result.itinerary.filter((stop) => stop.type !== "depot").length} delivery stops`;
    $("#result-distance").textContent = Number(result.distance_km).toFixed(2);
    $("#result-solver").textContent = result.solver_name;
    $("#result-duration").textContent = formatDuration(result.estimated_mins);
    $("#result-saved").textContent = Number(result.saved_km).toFixed(2);
    $("#result-saved-pct").textContent = `${Number(result.saved_pct).toFixed(1)}% below nearest-neighbor baseline (${Number(result.baseline_km).toFixed(2)} km)`;
    $("#result-runtime").textContent = Number(result.runtime_seconds).toFixed(4);
    $("#result-evaluations").textContent = Number(result.evaluations).toLocaleString();
    $("#route-node-count").textContent = `${Number(result.nodes_expanded).toLocaleString()} road nodes expanded · ${result.iterations} solver iterations`;
    $("#itinerary-summary").textContent = `${result.itinerary.length} route entries · ${state.settings.round_trip ? "return to depot" : "finish at last delivery"}`;
    $("#csp-tag").textContent = result.csp?.feasible ? "Constraints feasible" : "Constraint warning";
    $("#itinerary-body").innerHTML = result.itinerary.map((stop, index) => {
      const isDepot = stop.type === "depot";
      const status = deliveryStatus(stop.stop_index);
      const stopLabel = isDepot ? "Depot" : `Stop ${index}`;
      return `<tr>
        <td><strong>${stopLabel}</strong></td>
        <td><strong>${escapeHtml(stop.name)}</strong><small class="table-sub">${escapeHtml(stop.address)}</small></td>
        <td>${Number(stop.weight_kg || 0).toFixed(1)} kg</td>
        <td>${isDepot ? "—" : `<span class="badge ${stop.priority === "Urgent" ? "urgent" : ""}">${escapeHtml(stop.priority)}</span>`}</td>
        <td>${escapeHtml(stop.time_window || "Anytime")}</td>
        <td>${Number(stop.leg_distance_km || 0).toFixed(2)} km</td>
        <td><span class="status-pill ${statusClass(status)}">${escapeHtml(status)}</span></td>
      </tr>`;
    }).join("");
    drawRouteOnMap("results", result, state.stops);
    renderAgent(state.agent, state.simulation_active);
    drawConvergence(result);
    setTimeout(() => maps.results?.invalidateSize(), 80);
  }

  function deliveryStatus(stopIndex) {
    const agent = state?.agent;
    if (!agent) return stopIndex === 0 ? "Depot" : "Pending";
    if ((agent.delivered_indices || []).includes(stopIndex)) return "Delivered";
    if ((agent.skipped_indices || []).includes(stopIndex)) return "Skipped";
    return stopIndex === 0 ? "Depot" : "Pending";
  }

  function renderAgent(agent, active) {
    if (!agent) {
      $("#agent-action").textContent = "Run not started";
      $("#agent-goal").textContent = "Ready at depot";
      $("#agent-reason").textContent = "Start the run to enable delivery actions.";
      $("#agent-progress-label").textContent = "0%";
      $("#agent-progress-bar").style.width = "0%";
      $("#agent-cargo").textContent = "0.0";
      $("#agent-delivered").textContent = "0 / 0";
      $("#agent-skipped").textContent = "0";
      $("#delivery-actions").classList.add("hidden");
      $("#start-run").classList.remove("hidden");
      $("#start-run").disabled = false;
      $("#simulation-transport").classList.add("hidden");
      return;
    }
    $("#agent-action").textContent = agent.is_finished ? "Run complete" : active ? agent.action : "Ready to start";
    $("#agent-goal").textContent = agent.current_goal || "Tour complete";
    $("#agent-reason").textContent = agent.reason || "";
    $("#agent-progress-label").textContent = `${Math.round(agent.progress_pct || 0)}%`;
    $("#agent-progress-bar").style.width = `${Math.min(100, agent.progress_pct || 0)}%`;
    $("#agent-cargo").textContent = Number(agent.remaining_cargo_kg || 0).toFixed(1);
    $("#agent-delivered").textContent = `${agent.delivered_count || 0} / ${agent.total_deliveries || 0}`;
    $("#agent-skipped").textContent = agent.skipped_count || 0;
    const hasCurrentDelivery = active && simulation.arrived && !agent.is_finished && agent.current_goal_index !== 0;
    $("#delivery-actions").classList.toggle("hidden", !hasCurrentDelivery);
    $("#start-run").classList.toggle("hidden", Boolean(active) || Boolean(agent.is_finished));
    $("#start-run").disabled = Boolean(agent.is_finished);
    $("#start-run").textContent = agent.has_started ? "Resume delivery run" : "Start delivery run";
    $("#simulation-transport").classList.toggle("hidden", !active);
    $("#pause-run").textContent = simulation.paused ? "Resume movement" : "Pause movement";
    $("#pause-run").disabled = !active || simulation.arrived || (!simulation.timer && !simulation.paused);
    if (agent.is_finished) {
      $("#agent-action").textContent = "Tour complete";
      $("#agent-goal").textContent = "Returned to depot";
    }
  }

  async function startRun() {
    const data = await api("/api/simulation/start", { method: "POST", body: {} });
    renderState(data);
    simulation.coordinates = data.result?.coordinates || [];
    simulation.waypoint = 0;
    simulation.arrived = false;
    simulation.paused = false;
    animateToCurrentStop(data.agent);
    notify("Delivery run started.");
  }

  async function recordDelivery(action) {
    const response = await api("/api/simulation/action", { method: "POST", body: { action } });
    simulation.arrived = false;
    renderState(response);
    renderResults();
    if (response.agent?.is_finished) {
      if (state.settings.round_trip) animateReturnToDepot();
      else stopVehicle();
    } else {
      animateToCurrentStop(response.agent);
    }
    notify(action === "deliver" ? "Delivery marked complete." : "Stop skipped; package remains on board.");
  }

  function animateToCurrentStop(agent) {
    if (!agent || agent.is_finished || !maps.results || !state?.result) return;
    const stop = state.result.itinerary.find((item) =>
      item.stop_index === agent.current_goal_index && item.type !== "depot"
    );
    if (!stop || !simulation.coordinates.length) {
      simulation.arrived = true;
      renderAgent(agent, state.simulation_active);
      return;
    }
    let target = simulation.waypoint;
    let closest = Infinity;
    simulation.coordinates.forEach((point, index) => {
      if (index < simulation.waypoint) return;
      const distance = (point[0] - stop.latitude) ** 2 + (point[1] - stop.longitude) ** 2;
      if (distance < closest) {
        closest = distance;
        target = index;
      }
    });
    simulation.target = target;
    clearInterval(simulation.timer);
    if (!simulation.marker) {
      simulation.marker = L.marker(simulation.coordinates[simulation.waypoint], {
        icon: L.divIcon({ className: "", html: '<div class="map-vehicle">V</div>', iconSize: [25, 25], iconAnchor: [12, 12] }),
        zIndexOffset: 1000
      }).addTo(maps.results);
    } else {
      simulation.marker.setLatLng(simulation.coordinates[simulation.waypoint]);
      simulation.marker.addTo(maps.results);
    }
    const distance = Math.max(0, target - simulation.waypoint);
    const stride = Math.max(1, Math.ceil(distance / 180));
    if (!distance) {
      arriveAtStop(agent);
      return;
    }
    simulation.timer = setInterval(() => {
      simulation.waypoint = Math.min(simulation.target, simulation.waypoint + stride);
      simulation.marker.setLatLng(simulation.coordinates[simulation.waypoint]);
      if (simulation.waypoint >= simulation.target) {
        clearInterval(simulation.timer);
        simulation.timer = null;
        arriveAtStop(agent);
      }
    }, 24);
  }

  function arriveAtStop(agent) {
    clearInterval(simulation.timer);
    simulation.timer = null;
    simulation.arrived = true;
    if (agent) {
      agent.action = "ARRIVE_AT_STOP";
      agent.reason = `Arrived at ${agent.current_goal}. Record the delivery outcome to continue.`;
      renderAgent(agent, true);
    }
  }

  function stopVehicle() {
    clearInterval(simulation.timer);
    simulation.timer = null;
    simulation.paused = false;
    if (simulation.marker && maps.results) {
      maps.results.removeLayer(simulation.marker);
      simulation.marker = null;
    }
  }

  async function stopRun() {
    const data = await api("/api/simulation/stop", { method: "POST", body: {} });
    stopVehicle();
    simulation.arrived = false;
    renderState(data);
    notify("Delivery run stopped. Progress is saved for resume.");
  }

  function toggleMovementPause() {
    if (simulation.arrived || !state?.simulation_active) return;
    if (simulation.paused) {
      simulation.paused = false;
      animateToCurrentStop(state.agent);
    } else {
      clearInterval(simulation.timer);
      simulation.timer = null;
      simulation.paused = true;
    }
    renderAgent(state.agent, state.simulation_active);
  }

  function animateReturnToDepot() {
    const coordinates = simulation.coordinates;
    if (!coordinates.length || !simulation.marker) {
      stopVehicle();
      return;
    }
    const target = coordinates.length - 1;
    const stride = Math.max(1, Math.ceil((target - simulation.waypoint) / 140));
    clearInterval(simulation.timer);
    simulation.timer = setInterval(() => {
      simulation.waypoint = Math.min(target, simulation.waypoint + stride);
      simulation.marker.setLatLng(coordinates[simulation.waypoint]);
      if (simulation.waypoint >= target) {
        clearInterval(simulation.timer);
        simulation.timer = null;
      }
    }, 24);
  }

  async function saveRoute() {
    const response = await api("/api/save", { method: "POST", body: {} });
    notify(`Trip #${response.route_id} saved to history.`);
    updateDashboard(response.dashboard);
  }

  function chartColors() {
    const style = getComputedStyle(document.documentElement);
    return {
      text: style.getPropertyValue("--text-soft").trim(),
      muted: style.getPropertyValue("--muted").trim(),
      grid: style.getPropertyValue("--line").trim(),
      blue: style.getPropertyValue("--primary").trim(),
      green: style.getPropertyValue("--green").trim(),
      red: style.getPropertyValue("--red").trim()
    };
  }

  function destroyChart(key) {
    if (charts[key]) {
      charts[key].destroy();
      delete charts[key];
    }
  }

  function drawConvergence(result) {
    if (!window.Chart || !$("#convergence-chart") || !result) return;
    destroyChart("convergence");
    const colors = chartColors();
    charts.convergence = new Chart($("#convergence-chart"), {
      type: "line",
      data: {
        labels: result.convergence_history.map((_, index) => index + 1),
        datasets: [{
          data: result.convergence_history,
          borderColor: colors.blue,
          backgroundColor: colors.blue + "22",
          fill: true,
          tension: .22,
          pointRadius: result.convergence_history.length > 35 ? 0 : 2,
          borderWidth: 2
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { title: { display: true, text: "Recorded iteration", color: colors.muted }, ticks: { color: colors.muted, maxTicksLimit: 8 }, grid: { color: colors.grid } },
          y: { title: { display: true, text: "Distance (km)", color: colors.muted }, ticks: { color: colors.muted }, grid: { color: colors.grid } }
        }
      }
    });
  }

  async function refreshHistory() {
    try {
      historyRows = await api("/api/history");
      renderHistory();
    } catch (error) {
      notify(error.message, true);
    }
  }

  function renderHistory() {
    const filter = ($("#history-filter").value || "").trim().toLowerCase();
    const rows = historyRows.filter((route) =>
      `${route.route_name} ${route.depot_name} ${route.algorithm}`.toLowerCase().includes(filter)
    );
    $("#history-count").textContent = `${historyRows.length} saved route${historyRows.length === 1 ? "" : "s"} in the local SQLite database`;
    $("#history-body").innerHTML = rows.length ? rows.map((route) => `
      <tr>
        <td><strong>${escapeHtml(route.route_name)}</strong></td>
        <td>${escapeHtml(route.created_at)}</td>
        <td>${escapeHtml(route.depot_name)}</td>
        <td>${Number(route.num_stops) || 0}</td>
        <td>${Number(route.total_distance_km || 0).toFixed(2)} km</td>
        <td>${Number(route.saved_pct || 0).toFixed(1)}%</td>
        <td>${escapeHtml(route.algorithm)}</td>
        <td><span class="status-pill ${statusClass(route.status)}">${escapeHtml(route.status)}</span></td>
        <td><div class="row-actions">
          <button class="row-action" data-history-action="details" data-id="${route.id}">Inspect</button>
          <button class="row-action" data-history-action="load" data-id="${route.id}">Load</button>
          <button class="row-action delete" data-history-action="delete" data-id="${route.id}">Delete</button>
        </div></td>
      </tr>`).join("") : `<tr><td class="empty-cell" colspan="9">${historyRows.length ? "No trips match this filter." : "No saved routes yet."}</td></tr>`;
  }

  async function showHistoryDetails(routeId) {
    const data = await api(`/api/history/${routeId}`);
    $("#history-detail-title").textContent = data.route.route_name;
    $("#history-detail-meta").textContent = `${data.route.created_at} · ${data.route.total_distance_km.toFixed(2)} km · ${data.route.algorithm}`;
    $("#history-detail-stops").innerHTML = data.stops.map((stop, index) => `
      <div class="history-stop"><span class="stop-number ${index === 0 ? "depot" : ""}">${index === 0 ? "D" : index}</span>
        <div><strong>${escapeHtml(stop.name)}</strong><small>${escapeHtml(stop.address)} · ${Number(stop.weight_kg || 0).toFixed(1)} kg · ${escapeHtml(stop.priority)}</small></div>
        <span class="status-pill ${statusClass(stop.delivery_status)}">${escapeHtml(stop.delivery_status)}</span>
      </div>`).join("");
    $("#history-detail").classList.remove("hidden");
    $("#history-detail").scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  async function handleHistoryAction(button) {
    const id = button.dataset.id;
    const action = button.dataset.historyAction;
    if (action === "details") return showHistoryDetails(id);
    if (action === "load") {
      await applyPlannerResponse(await api(`/api/history/${id}/load`, { method: "POST", body: {} }));
      showView("planner");
      notify("Saved route loaded into the planner.");
      return;
    }
    if (action === "delete") {
      if (!window.confirm("Delete this saved trip and its stop history?")) return;
      await api(`/api/history/${id}`, { method: "DELETE" });
      await refreshHistory();
      await refreshState();
      $("#history-detail").classList.add("hidden");
      notify("Saved trip deleted.");
    }
  }

  async function refreshAnalytics() {
    try {
      const [data, zones] = await Promise.all([api("/api/analytics"), api("/api/zones")]);
      analyticsData = data;
      analyticsZones = zones;
      const summary = data.summary || {};
      $("#analytics-routes").textContent = summary.total_routes || 0;
      $("#analytics-distance").textContent = Number(summary.avg_distance || 0).toFixed(1);
      $("#analytics-savings").textContent = Number(summary.avg_saved_pct || 0).toFixed(1);
      $("#analytics-stops").textContent = Number(summary.total_stops_planned || 0);
      $("#model-r2").textContent = Number(data.model_metrics?.R2_score || 0).toFixed(3);
      $("#model-mae").textContent = Number(data.model_metrics?.MAE_mins || 0).toFixed(1);
      $("#model-samples").textContent = data.model_metrics?.Test_Samples || 0;
      historyRows = data.routes || [];
      drawAnalyticsCharts(data, zones);
    } catch (error) {
      notify(error.message, true);
    }
  }

  function drawAnalyticsCharts(data, zones) {
    if (!window.Chart || !$("#distance-chart") || !$("#solver-chart")) return;
    const routes = data?.routes || historyRows || [];
    const colors = chartColors();
    destroyChart("distance");
    destroyChart("solver");
    destroyChart("cluster");
    destroyChart("analyticsElbow");
    destroyChart("prediction");
    destroyChart("feature");
    const recent = routes.slice(0, 10).reverse();
    charts.distance = new Chart($("#distance-chart"), {
      type: "bar",
      data: {
        labels: recent.map((route) => `#${route.id}`),
        datasets: [
          { label: "Optimized", data: recent.map((route) => Number(route.total_distance_km || 0)), backgroundColor: colors.blue, borderRadius: 4 },
          { label: "Baseline", data: recent.map((route) => Number(route.baseline_distance_km || 0)), backgroundColor: colors.green, borderRadius: 4 }
        ]
      },
      options: chartOptions(colors, true, "Distance (km)")
    });
    const breakdown = data?.summary?.algorithm_breakdown || [];
    charts.solver = new Chart($("#solver-chart"), {
      type: "doughnut",
      data: {
        labels: breakdown.map((item) => item.algorithm),
        datasets: [{ data: breakdown.map((item) => Number(item.count || 0)), backgroundColor: [colors.blue, colors.green, "#c18a41", "#8b75c7", "#438e9e"], borderWidth: 0 }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "64%",
        plugins: {
          legend: { position: "bottom", labels: { color: colors.text, boxWidth: 9, usePointStyle: true, padding: 14, font: { size: 9 } } },
          tooltip: { enabled: true }
        }
      }
    });
    const deliveries = (zones?.stops || []).filter((stop) => stop.type !== "depot");
    const clusterIds = [...new Set(deliveries.map((stop) => Number(stop.cluster)).filter((id) => Number.isInteger(id) && id >= 0))];
    const clusterColors = ["#2563eb", "#e87824", "#16a184", "#c84c82", "#8358c4", "#cf9c2c"];
    const clusterDatasets = clusterIds.length
      ? clusterIds.map((id) => ({
        label: zones.clusters?.clusters?.[id]?.name || `Zone ${id + 1}`,
        data: deliveries.filter((stop) => Number(stop.cluster) === id).map((stop) => ({
          x: Number(stop.longitude), y: Number(stop.latitude)
        })),
        backgroundColor: zones.clusters?.clusters?.[id]?.color || clusterColors[id % clusterColors.length],
        pointRadius: 5
      }))
      : [{
        label: "Delivery stops",
        data: deliveries.map((stop) => ({ x: Number(stop.longitude), y: Number(stop.latitude) })),
        backgroundColor: "#8290a3",
        pointRadius: 5
      }];
    charts.cluster = new Chart($("#cluster-chart"), {
      type: "scatter",
      data: { datasets: clusterDatasets },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: "bottom", labels: { color: colors.text, boxWidth: 10, font: { size: 9 } } } },
        scales: {
          x: { title: { display: true, text: "Longitude", color: colors.text }, ticks: { color: colors.muted, maxTicksLimit: 5 }, grid: { color: colors.grid } },
          y: { title: { display: true, text: "Latitude", color: colors.text }, ticks: { color: colors.muted, maxTicksLimit: 5 }, grid: { color: colors.grid } }
        }
      }
    });
    charts.analyticsElbow = new Chart($("#analytics-elbow-chart"), {
      type: "line",
      data: {
        labels: zones?.k || [],
        datasets: [{
          label: "Within-zone distance",
          data: zones?.inertia || [],
          borderColor: "#7284a0",
          backgroundColor: "rgba(114,132,160,.12)",
          pointRadius: 3,
          tension: .2
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { title: { display: true, text: "Number of zones", color: colors.text }, ticks: { color: colors.muted }, grid: { color: colors.grid } },
          y: { title: { display: true, text: "Inertia", color: colors.text }, ticks: { color: colors.muted }, grid: { color: colors.grid } }
        }
      }
    });
    const actual = data.test_actual_mins || [];
    const predicted = data.test_predicted_mins || [];
    const modelPoints = actual.map((value, index) => ({ x: Number(value), y: Number(predicted[index]) }))
      .filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y));
    const axisMin = modelPoints.length ? Math.min(...modelPoints.map((point) => Math.min(point.x, point.y))) : 0;
    const axisMax = modelPoints.length ? Math.max(...modelPoints.map((point) => Math.max(point.x, point.y))) : 1;
    charts.prediction = new Chart($("#prediction-chart"), {
      type: "scatter",
      data: {
        datasets: [
          { label: "Test samples", data: modelPoints, backgroundColor: "#18a785", pointRadius: 3 },
          { label: "Perfect estimate", data: [{ x: axisMin, y: axisMin }, { x: axisMax, y: axisMax }], type: "line", borderColor: "#8a96a8", borderDash: [5, 4], pointRadius: 0 }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: "bottom", labels: { color: colors.text, boxWidth: 10, font: { size: 9 } } } },
        scales: {
          x: { title: { display: true, text: "Actual minutes", color: colors.text }, ticks: { color: colors.muted, maxTicksLimit: 5 }, grid: { color: colors.grid } },
          y: { title: { display: true, text: "Estimated minutes", color: colors.text }, ticks: { color: colors.muted, maxTicksLimit: 5 }, grid: { color: colors.grid } }
        }
      }
    });
    const importances = data.feature_importances || {};
    charts.feature = new Chart($("#feature-chart"), {
      type: "bar",
      data: {
        labels: Object.keys(importances).map((name) => name.replace(/_/g, " ")),
        datasets: [{ label: "Importance", data: Object.values(importances), backgroundColor: "#6485d8", borderRadius: 4 }]
      },
      options: {
        indexAxis: "y", responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { beginAtZero: true, ticks: { color: colors.muted, maxTicksLimit: 5 }, grid: { color: colors.grid } },
          y: { ticks: { color: colors.muted, font: { size: 9 } }, grid: { display: false } }
        }
      }
    });
    $("#cluster-chart-note").textContent = clusterIds.length
      ? `${deliveries.length} delivery stops grouped into ${clusterIds.length} active zones.`
      : "Create zones in Planner to see assigned groups. The elbow curve uses current delivery locations.";
  }

  function chartOptions(colors, legend, axisTitle) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: legend, position: "bottom", labels: { color: colors.text, boxWidth: 9, usePointStyle: true, font: { size: 9 } } } },
      scales: {
        x: { ticks: { color: colors.muted }, grid: { display: false } },
        y: { title: { display: true, text: axisTitle, color: colors.muted }, ticks: { color: colors.muted }, grid: { color: colors.grid }, beginAtZero: true }
      }
    };
  }

  async function refreshZones() {
    try {
      const data = await api("/api/zones");
      zoneData = data;
      if (!data.k?.length || !window.Chart) {
        drawElbowChart(data);
        return;
      }
      drawElbowChart(data);
    } catch (error) {
      notify(error.message, true);
    }
  }

  function drawElbowChart(data) {
    if (!window.Chart || !$("#elbow-chart")) return;
    if (!data?.k?.length) {
      destroyChart("elbow");
      return;
    }
    const colors = chartColors();
    destroyChart("elbow");
    charts.elbow = new Chart($("#elbow-chart"), {
      type: "line",
      data: {
        labels: data.k,
        datasets: [{ data: data.inertia, borderColor: colors.blue, backgroundColor: colors.blue + "22", fill: true, tension: .2, pointRadius: 3, borderWidth: 2 }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false }, title: { display: true, text: "Zone fit by cluster count", color: colors.text, align: "start", font: { size: 9, weight: "600" } } },
        scales: {
          x: { title: { display: true, text: "Zones (k)", color: colors.muted }, ticks: { color: colors.muted, font: { size: 8 } }, grid: { color: colors.grid } },
          y: { ticks: { color: colors.muted, font: { size: 8 } }, grid: { color: colors.grid } }
        }
      }
    });
  }

  function bindEvents() {
    $$("[data-nav]").forEach((button) => button.addEventListener("click", (event) => {
      event.preventDefault();
      showView(button.dataset.nav);
    }));
    $("#theme-toggle").addEventListener("click", () => {
      setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
    });
    $("#today-label").textContent = new Intl.DateTimeFormat(undefined, { weekday: "short", month: "short", day: "numeric" }).format(new Date());

    $("#place-search").addEventListener("input", (event) => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => searchPlaces(event.target.value), 250);
    });
    $("#search-results").addEventListener("click", (event) => {
      const button = event.target.closest("[data-search-index]");
      if (button) choosePlace($("#search-results")._places[Number(button.dataset.searchIndex)]);
    });
    $("#dismiss-place").addEventListener("click", clearSelection);
    $("#use-as-depot").addEventListener("click", () => setDepot().catch((error) => notify(error.message, true)));
    $("#use-as-delivery").addEventListener("click", openDeliveryEditor);
    $("#close-editor").addEventListener("click", () => {
      editingDeliveryIndex = null;
      $("#delivery-editor").classList.add("hidden");
    });
    $("#confirm-delivery").addEventListener("click", () => addDelivery().catch((error) => notify(error.message, true)));
    $("#delivery-editor").addEventListener("keydown", (event) => {
      if (event.key === "Enter") addDelivery().catch((error) => notify(error.message, true));
    });
    $("#stop-list").addEventListener("click", async (event) => {
      const button = event.target.closest("[data-action]");
      if (!button) return;
      try {
        if (button.dataset.action === "remove-depot") {
          await applyPlannerResponse(await api("/api/depot", { method: "DELETE" }));
          notify("Depot removed.");
        } else if (button.dataset.action === "edit-stop") {
          openDeliveryEditor(Number(button.dataset.index));
        } else {
          await applyPlannerResponse(await api(`/api/stops/${button.dataset.index}`, { method: "DELETE" }));
          notify("Delivery stop removed.");
        }
      } catch (error) {
        notify(error.message, true);
      }
    });
    $("#clear-route").addEventListener("click", async () => {
      if (state?.stops?.length && !window.confirm("Clear the depot and all delivery stops?")) return;
      try {
        await api("/api/stops", { method: "DELETE" });
        clearSelection();
        await refreshState();
        await refreshZones();
        notify("Planner cleared.");
      } catch (error) {
        notify(error.message, true);
      }
    });
    $("#clear-deliveries").addEventListener("click", async () => {
      if (!state?.deliveries?.length) return;
      try {
        await applyPlannerResponse(await api("/api/deliveries", { method: "DELETE" }));
        notify("Delivery stops removed.");
      } catch (error) {
        notify(error.message, true);
      }
    });
    $("#optimize-button").addEventListener("click", optimizeRoute);
    $("#cluster-button").addEventListener("click", async () => {
      try {
        await applyPlannerResponse(await api("/api/clusters", {
          method: "POST", body: { k: Number($("#zone-count").value) }
        }));
        notify("Delivery zones calculated.");
      } catch (error) {
        notify(error.message, true);
      }
    });
    $("#map-style").addEventListener("change", (event) => {
      setMapStyle(event.target.value);
      if ($("#setting-map")) $("#setting-map").value = event.target.value;
      saveSettings(false).catch((error) => notify(error.message, true));
    });
    $$(".sample-button").forEach((button) => button.addEventListener("click", async () => {
      try {
        const data = await api("/api/sample", { method: "POST", body: { count: Number(button.dataset.count) } });
        await applyPlannerResponse(data);
        showView("planner");
        notify(`${button.dataset.count}-stop sample loaded.`);
      } catch (error) {
        notify(error.message, true);
      }
    }));
    $("#save-route").addEventListener("click", () => saveRoute().catch((error) => notify(error.message, true)));
    $("#start-run").addEventListener("click", () => startRun().catch((error) => notify(error.message, true)));
    $("#pause-run").addEventListener("click", toggleMovementPause);
    $("#stop-run").addEventListener("click", () => stopRun().catch((error) => notify(error.message, true)));
    $("#mark-delivered").addEventListener("click", () => recordDelivery("deliver").catch((error) => notify(error.message, true)));
    $("#skip-delivery").addEventListener("click", () => recordDelivery("skip").catch((error) => notify(error.message, true)));
    $("#refresh-history").addEventListener("click", refreshHistory);
    $("#history-filter").addEventListener("input", renderHistory);
    $("#history-body").addEventListener("click", (event) => {
      const button = event.target.closest("[data-history-action]");
      if (button) handleHistoryAction(button).catch((error) => notify(error.message, true));
    });
    $("#close-history-detail").addEventListener("click", () => $("#history-detail").classList.add("hidden"));
    $("#refresh-analytics").addEventListener("click", refreshAnalytics);
    $("#save-settings").addEventListener("click", () => saveSettings(true).catch((error) => notify(error.message, true)));
  }

  async function saveSettings(showNotice) {
    const payload = {
      capacity_kg: Number($("#setting-capacity").value),
      speed_kmh: Number($("#setting-speed").value),
      service_mins: Number($("#setting-service").value),
      solver: $("#setting-solver").value,
      search_method: $("#setting-search").value,
      map_style: $("#setting-map").value,
      round_trip: $("#setting-round-trip").checked
    };
    const data = await api("/api/settings", { method: "POST", body: payload });
    renderState(data);
    if (showNotice) notify("Fleet settings saved.");
  }

  async function init() {
    setTheme(localStorage.getItem("route-desk-theme") || "light");
    initMaps();
    bindEvents();
    try {
      const initialState = await api("/api/state");
      renderState(initialState);
      if (initialState.simulation_active && initialState.agent) {
        simulation.coordinates = initialState.result?.coordinates || [];
        simulation.waypoint = 0;
        animateToCurrentStop(initialState.agent);
      }
    } catch (error) {
      notify(error.message, true);
    }
    setInterval(() => {
      if (state?.graph_status === "loading") refreshState().catch(() => {});
    }, 2500);
  }

  window.addEventListener("DOMContentLoaded", init);
})();
