"""Generate PDF versions of PROJECT_PROPOSAL and PROJECT_REPORT using ReportLab.

Ensures docs/ holds all 4 required files:
    1. PROJECT_PROPOSAL.md
    2. PROJECT_PROPOSAL.pdf
    3. PROJECT_REPORT.md
    4. PROJECT_REPORT.pdf
"""

import os
import sys
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
    HRFlowable
)

docs_dir = os.path.dirname(os.path.abspath(__file__))


def build_proposal_pdf():
    pdf_path = os.path.join(docs_dir, "PROJECT_PROPOSAL.pdf")
    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=letter,
        rightMargin=45,
        leftMargin=45,
        topMargin=45,
        bottomMargin=45
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#002B49"),
        spaceAfter=6
    )
    h2_style = ParagraphStyle(
        "DocH2",
        parent=styles["Heading2"],
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#005088"),
        spaceBefore=10,
        spaceAfter=4
    )
    body_style = ParagraphStyle(
        "DocBody",
        parent=styles["Normal"],
        fontSize=9.5,
        leading=13,
        spaceAfter=5
    )
    bold_body = ParagraphStyle(
        "DocBoldBody",
        parent=body_style,
        fontName="Helvetica-Bold"
    )

    story = []

    # Header
    story.append(Paragraph("FAST — NATIONAL UNIVERSITY OF COMPUTER AND EMERGING SCIENCES", bold_body))
    story.append(Paragraph("FAST School of Computing · Karachi Campus · Department of Software Engineering", body_style))
    story.append(Paragraph("AL-2002 Artificial Intelligence (Laboratory) · Fall 2026", body_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#002B49"), spaceAfter=10))

    story.append(Paragraph("PROJECT PROPOSAL", title_style))
    story.append(Paragraph("Semester Lab Project · Weightage 1 mark", body_style))
    story.append(Spacer(1, 8))

    # Group Information Table
    group_data = [
        [Paragraph("<b>Role</b>", bold_body), Paragraph("<b>Name</b>", bold_body), Paragraph("<b>Roll Number</b>", bold_body), Paragraph("<b>Section</b>", bold_body)],
        [Paragraph("Leader (solo)", body_style), Paragraph("Bisma Shahid", body_style), Paragraph("24K-3012", body_style), Paragraph("BSE-5A", body_style)],
        [Paragraph("<b>Project Title</b>", bold_body), Paragraph("Delivery Route Optimizer on a Real City Map", body_style), Paragraph("<b>Category</b>", bold_body), Paragraph("Part B — Applied / Data", body_style)],
        [Paragraph("<b>GitHub Repo</b>", bold_body), Paragraph("https://github.com/Bisma-404/Delivery-Route-Optimizer-on-a-Real-City-Map.git", body_style), Paragraph("<b>Submission</b>", bold_body), Paragraph("20/10/2026", body_style)]
    ]
    t = Table(group_data, colWidths=[90, 180, 90, 160])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#EAEFF5")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#B0C4DE")),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t)
    story.append(Spacer(1, 12))

    # 1. Project Title and Summary
    story.append(Paragraph("1. Project Title and Summary", h2_style))
    summary_text = (
        "<b>Title: Delivery Route Optimizer on a Real City Map</b><br/>"
        "This software helps a delivery rider or a small courier company plan the shortest possible route through 10 to 20 stops in "
        "a real city (Lahore). You give it a list of addresses and it finds a good order to visit them all, then draws the route on an interactive "
        "map. A plain program cannot do this well because the number of possible orderings grows astronomically — for 15 stops "
        "there are over a trillion ways to arrange them. The AI part is what makes it work: A* search finds the real road distance "
        "between every pair of stops, and then three different optimization algorithms compete to find the best visiting order. The "
        "user sees a map with the route drawn on it, a table comparing which algorithm did best, and how long each one took."
    )
    story.append(Paragraph(summary_text, body_style))

    # 2. Problem Statement
    story.append(Paragraph("2. Problem Statement and Motivation", h2_style))
    prob_text = (
        "Imagine you have 15 parcels to deliver across a city. Trying every single one by hand or by computer brute-force is computationally impossible. "
        "Small couriers in Pakistan typically rely on intuition or a simple 'nearest stop first' rule, which produces routes that are 20–40% longer "
        "than necessary. Solving this with AI metaheuristics saves real fuel, reduces transit time, and lowers carbon emissions."
    )
    story.append(Paragraph(prob_text, body_style))

    # 3. Problem Formulation
    story.append(Paragraph("3. Problem Formulation (PEAS & Environment)", h2_style))
    peas_data = [
        [Paragraph("<b>Component</b>", bold_body), Paragraph("<b>Description</b>", bold_body)],
        [Paragraph("Performance measure", body_style), Paragraph("Total route length in km (lower is better), and computation time in seconds.", body_style)],
        [Paragraph("Environment", body_style), Paragraph("Real road network of Lahore (Gulberg) loaded via OSMnx, plus 10–20 stops.", body_style)],
        [Paragraph("Actuators", body_style), Paragraph("Interactive map display with road polyline, stop markers, and comparison table.", body_style)],
        [Paragraph("Sensors", body_style), Paragraph("GPS coordinates and OpenStreetMap road network nodes and edge distances.", body_style)]
    ]
    t_peas = Table(peas_data, colWidths=[130, 390])
    t_peas.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#EAEFF5")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#B0C4DE")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(t_peas)

    # 4. Proposed AI Approach
    story.append(Paragraph("4. Proposed AI Approach", h2_style))
    ai_data = [
        [Paragraph("<b>#</b>", bold_body), Paragraph("<b>Technique</b>", bold_body), Paragraph("<b>Role</b>", bold_body), Paragraph("<b>Code Ownership</b>", bold_body)],
        [Paragraph("1", body_style), Paragraph("A* Search", body_style), Paragraph("Computes shortest road distance between pairs with Haversine heuristic", body_style), Paragraph("Own code (heapq)", body_style)],
        [Paragraph("2", body_style), Paragraph("Hill Climbing", body_style), Paragraph("Improves tour order using 2-opt inversion moves", body_style), Paragraph("Own code", body_style)],
        [Paragraph("3", body_style), Paragraph("Simulated Annealing", body_style), Paragraph("Explores order space, accepting worse moves early via Boltzmann P", body_style), Paragraph("Own code", body_style)],
        [Paragraph("4", body_style), Paragraph("Genetic Algorithm", body_style), Paragraph("Evolves population using Ordered Crossover (OX) and mutation", body_style), Paragraph("Own code", body_style)],
        [Paragraph("B", body_style), Paragraph("Nearest Neighbor", body_style), Paragraph("Baseline greedy rule (visiting closest unvisited stop)", body_style), Paragraph("Own code", body_style)]
    ]
    t_ai = Table(ai_data, colWidths=[20, 110, 270, 120])
    t_ai.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#EAEFF5")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#B0C4DE")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(t_ai)

    doc.build(story)
    print("Built:", pdf_path)


def build_report_pdf():
    pdf_path = os.path.join(docs_dir, "PROJECT_REPORT.pdf")
    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=letter,
        rightMargin=45,
        leftMargin=45,
        topMargin=45,
        bottomMargin=45
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#002B49"),
        spaceAfter=6
    )
    h2_style = ParagraphStyle(
        "DocH2",
        parent=styles["Heading2"],
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#005088"),
        spaceBefore=10,
        spaceAfter=4
    )
    body_style = ParagraphStyle(
        "DocBody",
        parent=styles["Normal"],
        fontSize=9,
        leading=12.5,
        spaceAfter=5
    )
    bold_body = ParagraphStyle(
        "DocBoldBody",
        parent=body_style,
        fontName="Helvetica-Bold"
    )

    story = []

    # Header
    story.append(Paragraph("FAST — NATIONAL UNIVERSITY OF COMPUTER AND EMERGING SCIENCES", bold_body))
    story.append(Paragraph("FAST School of Computing · Karachi Campus · Department of Software Engineering", body_style))
    story.append(Paragraph("AL-2002 Artificial Intelligence (Laboratory) · Fall 2026", body_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#002B49"), spaceAfter=10))

    story.append(Paragraph("PROJECT FINAL REPORT: DELIVERY ROUTE OPTIMIZER", title_style))
    story.append(Paragraph("Student: Bisma Shahid (24K-3012) · Section BSE-5A · Leader (solo)", bold_body))
    story.append(Paragraph("GitHub: https://github.com/Bisma-404/Delivery-Route-Optimizer-on-a-Real-City-Map.git", body_style))
    story.append(Spacer(1, 8))

    # Executive Summary
    story.append(Paragraph("1. Executive Summary", h2_style))
    story.append(Paragraph(
        "This project implements a complete Python desktop software 'Delivery Route Optimizer' solving urban delivery dispatching "
        "on the real road network of Lahore, Pakistan. Using OpenStreetMap data cached via OSMnx, the system integrates a custom "
        "A* search algorithm (with heapq and an admissible spherical Haversine heuristic) and four optimization techniques: "
        "Nearest Neighbor baseline, Hill Climbing (2-opt), Simulated Annealing, and a Genetic Algorithm. Results across 10 randomized "
        "test instances prove that Simulated Annealing and the Genetic Algorithm achieve up to 23.57% route length reduction.",
        body_style
    ))

    # 2. System Architecture
    story.append(Paragraph("2. System Architecture & Object-Oriented Design", h2_style))
    story.append(Paragraph(
        "The architecture adheres strictly to OOP modularity:<br/>"
        "• <b>RouteProblem</b>: Encapsulates stops, distance matrix, depot index, round-trip route length, and fitness (1/length).<br/>"
        "• <b>AStarPlanner</b>: Custom heapq A* implementation; Haversine heuristic; counts nodes expanded; extracts road curves.<br/>"
        "• <b>MetaheuristicSolver (ABC)</b>: Abstract base class with overridden <code>solve()</code> in 4 subclasses:<br/>"
        "  - NearestNeighborSolver (greedy baseline)<br/>"
        "  - HillClimbSolver (2-opt local search)<br/>"
        "  - SimulatedAnnealingSolver (geometric cooling schedule)<br/>"
        "  - GeneticSolver (Ordered Crossover OX, tournament selection, elitism)<br/>"
        "• <b>GraphLoader & StopGenerator</b>: Offline GraphML caching, largest SCC filtering (1,227 nodes), CSV coordinate snapping.<br/>"
        "• <b>Tkinter GUI & TkinterMapView</b>: Responsive UI with background threading and real road polylines.",
        body_style
    ))

    # 3. Admissibility Proof
    story.append(Paragraph("3. Mathematical Justification of Haversine Heuristic (Lab 05)", h2_style))
    story.append(Paragraph(
        "<b>Admissibility:</b> The Haversine formula computes the spherical great-circle distance between two GPS coordinates. "
        "On Earth's surface, the great-circle distance is the geometric lower bound of any physical path. Real vehicles must navigate "
        "along curved streets and intersections, so true road distance is always >= Haversine distance. Therefore, h(u, v) <= h*(u, v), "
        "making the heuristic strictly admissible.<br/>"
        "<b>Consistency:</b> Satisfies the spherical triangle inequality h(u, v) <= c(u, w) + h(w, v). "
        "Empirical testing demonstrates that A* achieves an identical optimal path to Uniform Cost Search while reducing expanded "
        "nodes by <b>60.7%</b> (279 nodes vs. 710 nodes).",
        body_style
    ))

    # 4. Experimental Results Table
    story.append(Paragraph("4. Experimental Benchmark Results (N=10 Instances, Seed=42)", h2_style))
    results_data = [
        [Paragraph("<b>Solver</b>", bold_body), Paragraph("<b>Mean Dist (km)</b>", bold_body), Paragraph("<b>Std Dev</b>", bold_body), Paragraph("<b>Mean Time (s)</b>", bold_body), Paragraph("<b>Mean Impr vs NN</b>", bold_body), Paragraph("<b>Peak Impr</b>", bold_body)],
        [Paragraph("Nearest Neighbor", body_style), Paragraph("19.40 km", body_style), Paragraph("1.64 km", body_style), Paragraph("0.00005 s", body_style), Paragraph("0.00% (Baseline)", body_style), Paragraph("0.00%", body_style)],
        [Paragraph("Hill Climbing", body_style), Paragraph("17.35 km", body_style), Paragraph("1.59 km", body_style), Paragraph("0.00287 s", body_style), Paragraph("10.52%", body_style), Paragraph("16.32%", body_style)],
        [Paragraph("Simulated Annealing", body_style), Paragraph("17.05 km", body_style), Paragraph("2.09 km", body_style), Paragraph("0.01530 s", body_style), Paragraph("12.26%", body_style), Paragraph("23.57%", body_style)],
        [Paragraph("Genetic Algorithm", body_style), Paragraph("17.08 km", body_style), Paragraph("1.86 km", body_style), Paragraph("0.24857 s", body_style), Paragraph("11.97%", body_style), Paragraph("23.25%", body_style)]
    ]
    t_res = Table(results_data, colWidths=[110, 85, 75, 80, 100, 70])
    t_res.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#EAEFF5")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#B0C4DE")),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(t_res)
    story.append(Spacer(1, 8))

    # 5. Generated Figures
    story.append(Paragraph("5. Generated Figures Summary", h2_style))
    story.append(Paragraph(
        "• <b>Figure 1 (1_avg_route_length.png)</b>: Bar chart confirming SA and GA achieve shortest route lengths (~17.05 km).<br/>"
        "• <b>Figure 2 (2_avg_runtime.png)</b>: Runtimes demonstrate high efficiency (SA in 0.015s, GA in 0.25s).<br/>"
        "• <b>Figure 3 (3_convergence_sa_ga.png)</b>: Convergence curves showing SA exploration/cooling and GA generational fitness evolution.<br/>"
        "• <b>Figure 4 (4_pct_improvement_vs_nn.png)</b>: Percentage savings vs. NN baseline with mean and peak bars.",
        body_style
    ))

    # 6. Contribution Table
    story.append(Paragraph("6. Student Contribution Table", h2_style))
    story.append(Paragraph(
        "<b>Bisma Shahid (24K-3012)</b>: 100% individual contribution across all modules, tests, experiments, GUI, and documentation.",
        body_style
    ))

    doc.build(story)
    print("Built:", pdf_path)


if __name__ == "__main__":
    build_proposal_pdf()
    build_report_pdf()
