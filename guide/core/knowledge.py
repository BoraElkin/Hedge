"""Knowledge base for procedures, safety rules, and trade-specific information."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Step:
    """A single step in a procedure."""

    number: int
    instruction: str
    details: str = ""
    warnings: list[str] = field(default_factory=list)
    tools_needed: list[str] = field(default_factory=list)
    verification: str = ""  # How to verify step is complete
    image_hints: list[str] = field(default_factory=list)  # What to look for visually


@dataclass
class Procedure:
    """A complete procedure for a task."""

    id: str
    name: str
    trade: str
    description: str
    steps: list[Step]
    safety_warnings: list[str] = field(default_factory=list)
    tools_required: list[str] = field(default_factory=list)
    estimated_time: str = ""
    difficulty: str = "intermediate"  # beginner, intermediate, advanced
    tags: list[str] = field(default_factory=list)


@dataclass
class SafetyRule:
    """A safety rule or warning."""

    id: str
    trade: str
    category: str  # e.g., "electrical", "chemical", "physical"
    rule: str
    severity: str  # "critical", "warning", "caution"
    when_applicable: str = ""  # Conditions when this rule applies


class KnowledgeBase:
    """In-memory knowledge base for procedures and safety information.

    In production, this would be backed by a vector database for semantic search.
    For now, we use a simple in-memory store with keyword matching.
    """

    def __init__(self) -> None:
        self._procedures: dict[str, Procedure] = {}
        self._safety_rules: list[SafetyRule] = []
        self._parts_db: dict[str, dict[str, Any]] = {}
        self._load_default_knowledge()

    def add_procedure(self, procedure: Procedure) -> None:
        """Add a procedure to the knowledge base."""
        self._procedures[procedure.id] = procedure

    def get_procedure(self, procedure_id: str) -> Procedure | None:
        """Get a procedure by ID."""
        return self._procedures.get(procedure_id)

    def search_procedures(
        self,
        query: str,
        trade: str | None = None,
        limit: int = 5,
    ) -> list[Procedure]:
        """Search for procedures matching a query."""
        query_lower = query.lower()
        results = []

        for proc in self._procedures.values():
            if trade and proc.trade != trade:
                continue

            score = 0
            # Check name
            if query_lower in proc.name.lower():
                score += 10
            # Check description
            if query_lower in proc.description.lower():
                score += 5
            # Check tags
            for tag in proc.tags:
                if query_lower in tag.lower():
                    score += 3

            if score > 0:
                results.append((score, proc))

        results.sort(key=lambda x: x[0], reverse=True)
        return [proc for _, proc in results[:limit]]

    def get_safety_rules(
        self,
        trade: str | None = None,
        category: str | None = None,
    ) -> list[SafetyRule]:
        """Get applicable safety rules."""
        rules = self._safety_rules

        if trade:
            rules = [r for r in rules if r.trade == trade or r.trade == "general"]
        if category:
            rules = [r for r in rules if r.category == category]

        # Sort by severity (critical first)
        severity_order = {"critical": 0, "warning": 1, "caution": 2}
        rules.sort(key=lambda r: severity_order.get(r.severity, 3))

        return rules

    def get_critical_safety_rules(self, trade: str) -> list[SafetyRule]:
        """Get critical safety rules that must always be shown."""
        return [
            r for r in self._safety_rules
            if r.severity == "critical" and (r.trade == trade or r.trade == "general")
        ]

    def lookup_part(self, part_number: str) -> dict[str, Any] | None:
        """Look up a part by part number."""
        return self._parts_db.get(part_number)

    def _load_default_knowledge(self) -> None:
        """Load built-in knowledge base content."""
        self._load_safety_rules()
        self._load_hvac_procedures()
        self._load_plumbing_procedures()
        self._load_electrical_procedures()

    def _load_safety_rules(self) -> None:
        """Load default safety rules."""
        self._safety_rules = [
            # General
            SafetyRule(
                id="gen-001",
                trade="general",
                category="physical",
                rule="Always wear appropriate PPE (safety glasses, gloves) for the task",
                severity="warning",
            ),
            SafetyRule(
                id="gen-002",
                trade="general",
                category="physical",
                rule="Ensure adequate lighting before starting work",
                severity="caution",
            ),
            # Electrical
            SafetyRule(
                id="elec-001",
                trade="electrical",
                category="electrical",
                rule="ALWAYS verify power is OFF using a non-contact voltage tester before touching any wires",
                severity="critical",
            ),
            SafetyRule(
                id="elec-002",
                trade="electrical",
                category="electrical",
                rule="Lock out/tag out the breaker when working on circuits",
                severity="critical",
            ),
            SafetyRule(
                id="elec-003",
                trade="electrical",
                category="electrical",
                rule="Never work on electrical systems in wet conditions",
                severity="critical",
            ),
            # HVAC
            SafetyRule(
                id="hvac-001",
                trade="hvac",
                category="chemical",
                rule="Refrigerants require EPA 608 certification to handle",
                severity="critical",
            ),
            SafetyRule(
                id="hvac-002",
                trade="hvac",
                category="electrical",
                rule="Disconnect power before working on HVAC equipment",
                severity="critical",
            ),
            SafetyRule(
                id="hvac-003",
                trade="hvac",
                category="physical",
                rule="Capacitors can hold lethal charge - discharge before handling",
                severity="critical",
            ),
            # Plumbing
            SafetyRule(
                id="plumb-001",
                trade="plumbing",
                category="physical",
                rule="Turn off water supply before opening any connections",
                severity="warning",
            ),
            SafetyRule(
                id="plumb-002",
                trade="plumbing",
                category="chemical",
                rule="Never mix different drain cleaners - can create toxic gases",
                severity="critical",
            ),
        ]

    def _load_hvac_procedures(self) -> None:
        """Load HVAC procedures."""
        self.add_procedure(Procedure(
            id="hvac-filter-replace",
            name="Replace Air Filter",
            trade="hvac",
            description="Replace the air filter in a residential HVAC system",
            difficulty="beginner",
            estimated_time="5-10 minutes",
            tools_required=["New filter (correct size)", "Flashlight (optional)"],
            safety_warnings=["Turn off HVAC system before replacing filter"],
            tags=["filter", "maintenance", "air quality", "basic"],
            steps=[
                Step(
                    number=1,
                    instruction="Turn off the HVAC system",
                    details="Switch the thermostat to OFF or turn off the system at the breaker",
                    verification="System fan should not be running",
                ),
                Step(
                    number=2,
                    instruction="Locate the air filter",
                    details="Usually found in return air duct, air handler, or furnace compartment",
                    image_hints=["rectangular slot", "filter grille", "return vent"],
                ),
                Step(
                    number=3,
                    instruction="Remove the old filter",
                    details="Note the airflow direction arrow on the filter frame",
                    warnings=["Old filter may be dirty - avoid shaking dust into air"],
                    verification="Filter slides out easily",
                ),
                Step(
                    number=4,
                    instruction="Check filter size",
                    details="Size is printed on filter frame (e.g., 20x25x1)",
                    verification="New filter matches old filter dimensions",
                ),
                Step(
                    number=5,
                    instruction="Install new filter",
                    details="Arrow on filter should point toward the furnace/air handler (direction of airflow)",
                    warnings=["Incorrect direction reduces efficiency"],
                    verification="Filter fits snugly with no gaps around edges",
                ),
                Step(
                    number=6,
                    instruction="Turn system back on",
                    details="Set thermostat back to desired setting",
                    verification="System starts and air flows normally",
                ),
            ],
        ))

        self.add_procedure(Procedure(
            id="hvac-thermostat-install",
            name="Install Smart Thermostat",
            trade="hvac",
            description="Replace an old thermostat with a smart thermostat",
            difficulty="intermediate",
            estimated_time="30-45 minutes",
            tools_required=[
                "Screwdriver set",
                "Wire stripper",
                "Voltage tester",
                "Level",
                "Drill (if needed)",
                "Phone/tablet for setup",
            ],
            safety_warnings=[
                "Turn off power at breaker before starting",
                "Take photo of existing wiring before disconnecting",
            ],
            tags=["thermostat", "smart home", "installation", "wiring"],
            steps=[
                Step(
                    number=1,
                    instruction="Turn off power to HVAC system",
                    details="Flip the breaker for furnace/AC - usually labeled",
                    warnings=["Verify power is off with voltage tester"],
                    verification="Thermostat display is off",
                ),
                Step(
                    number=2,
                    instruction="Remove old thermostat faceplate",
                    details="Usually pulls straight off or has a release tab",
                    image_hints=["wires visible", "mounting plate", "wire terminals"],
                ),
                Step(
                    number=3,
                    instruction="Photograph existing wiring",
                    details="Take a clear photo showing which wire connects to which terminal (R, G, Y, W, C, etc.)",
                    warnings=["This photo is critical for correct installation"],
                    verification="Photo clearly shows wire colors and terminal labels",
                ),
                Step(
                    number=4,
                    instruction="Label each wire",
                    details="Use the labels included with new thermostat or tape",
                    verification="Each wire has a label matching its terminal",
                ),
                Step(
                    number=5,
                    instruction="Disconnect and remove old thermostat",
                    details="Unscrew wires from terminals, then remove mounting plate",
                    warnings=["Don't let wires fall back into wall"],
                    verification="Wall plate removed, wires accessible",
                ),
                Step(
                    number=6,
                    instruction="Install new mounting plate",
                    details="Use level to ensure it's straight, mark holes, drill if needed",
                    verification="Plate is level and secure",
                ),
                Step(
                    number=7,
                    instruction="Connect wires to new thermostat",
                    details="Match wire labels to terminals on new thermostat. Common: R=power, G=fan, Y=cooling, W=heating, C=common",
                    warnings=["Double-check connections against photo"],
                    verification="All wires securely connected to correct terminals",
                ),
                Step(
                    number=8,
                    instruction="Attach thermostat to mounting plate",
                    details="Snap or screw thermostat onto plate",
                    verification="Thermostat is secure and flush with wall",
                ),
                Step(
                    number=9,
                    instruction="Restore power and test",
                    details="Turn breaker back on, follow thermostat setup wizard",
                    verification="Thermostat powers on and responds to commands",
                ),
            ],
        ))

    def _load_plumbing_procedures(self) -> None:
        """Load plumbing procedures."""
        self.add_procedure(Procedure(
            id="plumb-faucet-cartridge",
            name="Replace Faucet Cartridge",
            trade="plumbing",
            description="Replace a leaking faucet cartridge in a single-handle faucet",
            difficulty="intermediate",
            estimated_time="30-60 minutes",
            tools_required=[
                "Adjustable wrench",
                "Allen wrench set",
                "Screwdriver",
                "Replacement cartridge",
                "Plumber's grease",
                "Towels",
            ],
            safety_warnings=["Turn off water supply before starting"],
            tags=["faucet", "leak", "cartridge", "repair"],
            steps=[
                Step(
                    number=1,
                    instruction="Turn off water supply",
                    details="Close shut-off valves under sink (turn clockwise)",
                    verification="No water flows when faucet is opened",
                ),
                Step(
                    number=2,
                    instruction="Open faucet to release pressure",
                    details="Turn handle to open position to drain remaining water",
                    verification="No more water drips from faucet",
                ),
                Step(
                    number=3,
                    instruction="Remove handle cap and screw",
                    details="Pop off decorative cap, remove Allen or Phillips screw underneath",
                    image_hints=["small cap on handle", "set screw"],
                    verification="Handle is loose",
                ),
                Step(
                    number=4,
                    instruction="Remove handle",
                    details="Pull handle straight up and off",
                    verification="Handle removed, cartridge visible",
                ),
                Step(
                    number=5,
                    instruction="Remove cartridge retaining clip or nut",
                    details="Look for a U-shaped clip or bonnet nut holding cartridge",
                    tools_needed=["Needle-nose pliers", "Wrench"],
                    verification="Cartridge can move freely",
                ),
                Step(
                    number=6,
                    instruction="Remove old cartridge",
                    details="Pull straight up - may need cartridge puller if stuck",
                    warnings=["Note cartridge orientation before removing"],
                    verification="Cartridge removed, valve body visible",
                ),
                Step(
                    number=7,
                    instruction="Install new cartridge",
                    details="Apply plumber's grease to O-rings, align tabs, push in",
                    warnings=["Ensure correct orientation - tabs must align"],
                    verification="Cartridge fully seated",
                ),
                Step(
                    number=8,
                    instruction="Reassemble in reverse order",
                    details="Retaining clip/nut, handle, screw, cap",
                    verification="All parts secure",
                ),
                Step(
                    number=9,
                    instruction="Turn water back on and test",
                    details="Slowly open shut-off valves, check for leaks",
                    verification="No leaks, faucet operates smoothly",
                ),
            ],
        ))

    def _load_electrical_procedures(self) -> None:
        """Load electrical procedures."""
        self.add_procedure(Procedure(
            id="elec-outlet-replace",
            name="Replace Electrical Outlet",
            trade="electrical",
            description="Replace a standard electrical outlet (receptacle)",
            difficulty="intermediate",
            estimated_time="15-30 minutes",
            tools_required=[
                "Non-contact voltage tester",
                "Screwdriver (flathead and Phillips)",
                "Needle-nose pliers",
                "Wire stripper",
                "New outlet (matching amperage)",
            ],
            safety_warnings=[
                "CRITICAL: Turn off power at breaker first",
                "CRITICAL: Verify power is off with voltage tester",
                "Do not work on aluminum wiring without proper training",
            ],
            tags=["outlet", "receptacle", "replacement", "electrical"],
            steps=[
                Step(
                    number=1,
                    instruction="Turn off power at breaker",
                    details="Locate correct breaker and flip to OFF position",
                    warnings=["If unsure which breaker, turn off main"],
                    verification="Breaker is in OFF position",
                ),
                Step(
                    number=2,
                    instruction="Verify power is OFF",
                    details="Use non-contact voltage tester on outlet",
                    warnings=["NEVER skip this step - test MUST show no voltage"],
                    tools_needed=["Non-contact voltage tester"],
                    verification="Tester shows NO voltage present",
                    image_hints=["voltage tester", "outlet slots"],
                ),
                Step(
                    number=3,
                    instruction="Remove outlet cover plate",
                    details="Remove single screw holding cover plate",
                    verification="Cover plate removed",
                ),
                Step(
                    number=4,
                    instruction="Remove outlet from box",
                    details="Remove two screws (top and bottom) holding outlet to box",
                    verification="Outlet can be pulled forward",
                ),
                Step(
                    number=5,
                    instruction="Test wires again",
                    details="Touch voltage tester to each wire",
                    warnings=["Final safety check before touching wires"],
                    verification="No voltage on any wire",
                ),
                Step(
                    number=6,
                    instruction="Note wire connections",
                    details="Black (hot) to brass screw, White (neutral) to silver screw, Green/bare (ground) to green screw",
                    warnings=["Take photo if helpful"],
                    verification="You know which wire goes where",
                ),
                Step(
                    number=7,
                    instruction="Disconnect wires from old outlet",
                    details="Loosen screws or release push-in connectors (insert screwdriver in release slot)",
                    verification="All wires disconnected",
                ),
                Step(
                    number=8,
                    instruction="Connect wires to new outlet",
                    details="Black→brass, White→silver, Ground→green. Wrap wire clockwise around screw",
                    warnings=["Ensure no bare copper visible outside terminals"],
                    verification="All connections tight, no exposed wire",
                ),
                Step(
                    number=9,
                    instruction="Secure outlet in box",
                    details="Push outlet into box, tighten mounting screws",
                    warnings=["Don't overtighten - can crack outlet"],
                    verification="Outlet is flush and secure",
                ),
                Step(
                    number=10,
                    instruction="Install cover plate",
                    details="Attach cover plate with screw",
                    verification="Cover plate secure and straight",
                ),
                Step(
                    number=11,
                    instruction="Restore power and test",
                    details="Turn breaker ON, test outlet with lamp or tester",
                    verification="Outlet works correctly",
                ),
            ],
        ))
