"""
Phase 4.3: Historical Client Scan Attribution Regression Tests.

Tests verify that scan events are attributed to the client whose assignment
was active when the scan occurred, NOT the current owner of the QR code.
"""
import os
os.environ["TESTING"] = "1"

import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base, get_db
from app.auth import hash_password
from app.models import (
    User, UserRole, QRCode, QRStatus,
    QRAssignment, QRScanEvent,
)
from app.services.client_service import (
    get_distinct_client_names,
    _get_client_qr_ids,
    _attribute_scan_to_client,
    _get_historical_scan_attribution,
    _count_historical_scans,
    get_clients_list,
    get_client_details,
    get_client_analytics,
)

DB_PATH = "./test_phase4_3_attribution.db"
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestSession()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    """Set up test database with a realistic QR transfer scenario."""
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestSession()

    # Create admin user
    admin = User(
        username="admin",
        password_hash=hash_password("admin123"),
        display_name="Test Admin",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db.add(admin)
    db.commit()

    # Create two QR codes
    qr1 = QRCode(
        qr_id="QR-TEST-001",
        token="tok_test_001",
        status=QRStatus.ACTIVE,
        current_business_name="Client B",
        current_destination="https://clientb.example.com",
        created_at=datetime(2026, 1, 1),
    )
    qr2 = QRCode(
        qr_id="QR-TEST-002",
        token="tok_test_002",
        status=QRStatus.ACTIVE,
        current_business_name="Client B",
        current_destination="https://clientb.example.com",
        created_at=datetime(2026, 1, 1),
    )
    qr3 = QRCode(
        qr_id="QR-TEST-003",
        token="tok_test_003",
        status=QRStatus.ACTIVE,
        current_business_name="Client C",
        current_destination="https://clientc.example.com",
        created_at=datetime(2026, 1, 1),
    )
    db.add_all([qr1, qr2, qr3])
    db.commit()

    # --- QR-TEST-001 Assignment History ---
    # Phase 1: Assigned to Client A (Jan 1 - Jan 15)
    a1 = QRAssignment(
        qr_code_id=qr1.id,
        business_name="Client A",
        destination_url="https://clienta.example.com",
        is_active=False,
        assigned_by=admin.id,
        assigned_at=datetime(2026, 1, 1, 10, 0, 0),
        deactivated_at=datetime(2026, 1, 15, 10, 0, 0),
    )
    # Phase 2: Transferred to Client B (Jan 15 - active)
    a2 = QRAssignment(
        qr_code_id=qr1.id,
        business_name="Client B",
        destination_url="https://clientb.example.com",
        is_active=True,
        assigned_by=admin.id,
        assigned_at=datetime(2026, 1, 15, 10, 0, 0),
    )
    db.add_all([a1, a2])

    # --- QR-TEST-002 Assignment History ---
    # Always Client B
    a3 = QRAssignment(
        qr_code_id=qr2.id,
        business_name="Client B",
        destination_url="https://clientb.example.com",
        is_active=True,
        assigned_by=admin.id,
        assigned_at=datetime(2026, 1, 5, 10, 0, 0),
    )
    db.add(a3)

    # --- QR-TEST-003 Assignment History ---
    # Always Client C (no transfer, control group)
    a4 = QRAssignment(
        qr_code_id=qr3.id,
        business_name="Client C",
        destination_url="https://clientc.example.com",
        is_active=True,
        assigned_by=admin.id,
        assigned_at=datetime(2026, 1, 1, 10, 0, 0),
    )
    db.add(a4)
    db.commit()

    # --- Scan Events ---
    now = datetime.utcnow()

    # Scans on QR-TEST-001 while assigned to Client A (before Jan 15)
    scan1 = QRScanEvent(
        qr_code_id=qr1.id,
        scanned_at=datetime(2026, 1, 5, 12, 0, 0),
        result_type="redirect",
    )
    scan2 = QRScanEvent(
        qr_code_id=qr1.id,
        scanned_at=datetime(2026, 1, 10, 14, 0, 0),
        result_type="redirect",
    )
    scan3 = QRScanEvent(
        qr_code_id=qr1.id,
        scanned_at=datetime(2026, 1, 12, 8, 0, 0),
        result_type="redirect",
    )
    # Scans on QR-TEST-001 while assigned to Client B (after Jan 15)
    scan4 = QRScanEvent(
        qr_code_id=qr1.id,
        scanned_at=datetime(2026, 1, 20, 10, 0, 0),
        result_type="redirect",
    )
    scan5 = QRScanEvent(
        qr_code_id=qr1.id,
        scanned_at=datetime(2026, 1, 25, 16, 0, 0),
        result_type="redirect",
    )
    # An unassigned attempt (should NOT count as redirect)
    scan6 = QRScanEvent(
        qr_code_id=qr1.id,
        scanned_at=datetime(2026, 1, 6, 9, 0, 0),
        result_type="unassigned",
    )
    # A disabled attempt (should NOT count)
    scan7 = QRScanEvent(
        qr_code_id=qr1.id,
        scanned_at=datetime(2026, 1, 7, 11, 0, 0),
        result_type="disabled",
    )
    # Scans on QR-TEST-002 (always Client B)
    scan8 = QRScanEvent(
        qr_code_id=qr2.id,
        scanned_at=datetime(2026, 1, 8, 10, 0, 0),
        result_type="redirect",
    )
    # Scans on QR-TEST-003 (always Client C)
    scan9 = QRScanEvent(
        qr_code_id=qr3.id,
        scanned_at=datetime(2026, 1, 9, 10, 0, 0),
        result_type="redirect",
    )
    scan10 = QRScanEvent(
        qr_code_id=qr3.id,
        scanned_at=datetime(2026, 1, 11, 10, 0, 0),
        result_type="redirect",
    )

    db.add_all([scan1, scan2, scan3, scan4, scan5, scan6, scan7, scan8, scan9, scan10])
    db.commit()
    db.close()
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    app.dependency_overrides.clear()
    try:
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
    except Exception:
        pass


def get_db_session():
    return TestSession()


# =====================================================================
# TEST: Historical attribution of individual scan events
# =====================================================================

class TestScanAttribution:
    """Verify _attribute_scan_to_client returns the correct historical owner."""

    def test_scan_during_client_a_assignment_attributed_to_client_a(self):
        db = get_db_session()
        # scan1: QR-TEST-001, Jan 5 (Client A assignment: Jan 1 - Jan 15)
        scan = db.query(QRScanEvent).filter(
            QRScanEvent.qr_code_id == 1,
            QRScanEvent.result_type == "redirect",
        ).order_by(QRScanEvent.scanned_at).first()
        owner = _attribute_scan_to_client(db, scan)
        assert owner == "Client A", f"Expected Client A, got {owner}"
        db.close()

    def test_scan_after_transfer_attributed_to_client_b(self):
        db = get_db_session()
        # scan4: QR-TEST-001, Jan 20 (Client B assignment: Jan 15+)
        scans = db.query(QRScanEvent).filter(
            QRScanEvent.qr_code_id == 1,
            QRScanEvent.result_type == "redirect",
        ).order_by(QRScanEvent.scanned_at).all()
        # 4th redirect on QR-TEST-001 = index 3
        scan = scans[3]
        owner = _attribute_scan_to_client(db, scan)
        assert owner == "Client B", f"Expected Client B, got {owner}"
        db.close()

    def test_all_client_a_scans_before_transfer(self):
        db = get_db_session()
        scans = _get_historical_scan_attribution(db, "Client A")
        assert len(scans) == 3, f"Client A should have 3 attributed scans, got {len(scans)}"
        for s in scans:
            assert s.scanned_at < datetime(2026, 1, 15, 10, 0, 0), \
                f"Client A scan at {s.scanned_at} should be before transfer"
        db.close()

    def test_all_client_b_scans_include_post_transfer_and_own_qr(self):
        db = get_db_session()
        scans = _get_historical_scan_attribution(db, "Client B")
        # 2 scans on QR-TEST-001 after transfer + 1 scan on QR-TEST-002 = 3
        assert len(scans) == 3, f"Client B should have 3 attributed scans, got {len(scans)}"
        db.close()

    def test_client_c_scans_unaffected_by_transfers(self):
        db = get_db_session()
        scans = _get_historical_scan_attribution(db, "Client C")
        assert len(scans) == 2, f"Client C should have 2 attributed scans, got {len(scans)}"
        db.close()


# =====================================================================
# TEST: Unassigned and disabled events are NOT counted as redirects
# =====================================================================

class TestNonRedirectExclusion:

    def test_unassigned_attempts_excluded(self):
        db = get_db_session()
        total_a = _count_historical_scans(db, "Client A")
        total_b = _count_historical_scans(db, "Client B")
        total_c = _count_historical_scans(db, "Client C")
        # Total redirects: 3 (A) + 3 (B) + 2 (C) = 8
        # scan6 (unassigned) and scan7 (disabled) must NOT be counted
        assert total_a + total_b + total_c == 8
        db.close()

    def test_total_scan_events_includes_non_redirects(self):
        db = get_db_session()
        all_events = db.query(QRScanEvent).count()
        redirect_events = db.query(QRScanEvent).filter(
            QRScanEvent.result_type == "redirect"
        ).count()
        assert all_events == 10  # 8 redirects + 1 unassigned + 1 disabled
        assert redirect_events == 8
        db.close()


# =====================================================================
# TEST: Each redirect is attributed exactly once
# =====================================================================

class TestExactlyOnceAttribution:

    def test_no_double_counting(self):
        db = get_db_session()
        all_clients = get_distinct_client_names(db)
        total = 0
        attributed_scan_ids = set()
        for name in all_clients:
            scans = _get_historical_scan_attribution(db, name)
            for s in scans:
                assert s.id not in attributed_scan_ids, \
                    f"Scan {s.id} double-attributed to {name}"
                attributed_scan_ids.add(s.id)
            total += len(scans)

        # Should match total redirect count exactly
        redirect_count = db.query(QRScanEvent).filter(
            QRScanEvent.result_type == "redirect"
        ).count()
        assert total == redirect_count, \
            f"Total attributed ({total}) != total redirects ({redirect_count})"
        db.close()


# =====================================================================
# TEST: Client list API uses historical attribution
# =====================================================================

class TestClientListAttribution:

    def test_clients_list_shows_historical_clients(self):
        db = get_db_session()
        result = get_clients_list(db)
        client_names = [item["client_name"] for item in result["items"]]
        # Client A has no current QRs but has historical scans
        assert "Client A" in client_names, \
            "Client A should appear in client list (has historical scans)"
        db.close()

    def test_clients_list_correct_scan_counts(self):
        db = get_db_session()
        result = get_clients_list(db)
        counts = {item["client_name"]: item["total_scans"] for item in result["items"]}
        assert counts.get("Client A") == 3, f"Client A: expected 3, got {counts.get('Client A')}"
        assert counts.get("Client B") == 3, f"Client B: expected 3, got {counts.get('Client B')}"
        assert counts.get("Client C") == 2, f"Client C: expected 2, got {counts.get('Client C')}"
        db.close()

    def test_clients_list_correct_qr_counts(self):
        db = get_db_session()
        result = get_clients_list(db)
        qr_counts = {item["client_name"]: item["total_qr_codes"] for item in result["items"]}
        # Client A has 0 current QRs (QR was transferred to B)
        assert qr_counts.get("Client A") == 0
        # Client B has QR-TEST-001 + QR-TEST-002 = 2
        assert qr_counts.get("Client B") == 2
        # Client C has QR-TEST-003 = 1
        assert qr_counts.get("Client C") == 1
        db.close()


# =====================================================================
# TEST: Client detail API uses historical attribution
# =====================================================================

class TestClientDetailAttribution:

    def test_client_a_detail_shows_historical_scans_no_qrs(self):
        db = get_db_session()
        detail = get_client_details(db, "Client A")
        assert detail["total_scans"] == 3
        assert detail["total_qr_codes"] == 0
        # No QR items since client A has no current QRs
        assert len(detail["items"]) == 0
        db.close()

    def test_client_b_detail_shows_only_own_scans(self):
        db = get_db_session()
        detail = get_client_details(db, "Client B")
        assert detail["total_scans"] == 3
        assert detail["total_qr_codes"] == 2
        db.close()

    def test_client_b_per_qr_scans_exclude_client_a_history(self):
        db = get_db_session()
        detail = get_client_details(db, "Client B")
        qr_items = {item["qr_id"]: item for item in detail["items"]}
        # QR-TEST-001 was transferred from A to B:
        # Client B should see only 2 scans on it (post-transfer), not all 5
        qr1_item = qr_items.get("QR-TEST-001")
        assert qr1_item is not None
        assert qr1_item["total_scans"] == 2, \
            f"QR-TEST-001 under Client B should have 2 scans, got {qr1_item['total_scans']}"
        # QR-TEST-002 always belonged to B: 1 scan
        qr2_item = qr_items.get("QR-TEST-002")
        assert qr2_item is not None
        assert qr2_item["total_scans"] == 1
        db.close()


# =====================================================================
# TEST: Client analytics API uses historical attribution
# =====================================================================

class TestClientAnalyticsAttribution:

    def test_analytics_client_a_daily_total(self):
        db = get_db_session()
        analytics = get_client_analytics(db, "Client A", days=365)
        daily_total = sum(d["scans"] for d in analytics["daily_scans"])
        assert daily_total == 3, f"Client A daily total should be 3, got {daily_total}"
        db.close()

    def test_analytics_client_b_daily_total(self):
        db = get_db_session()
        analytics = get_client_analytics(db, "Client B", days=365)
        daily_total = sum(d["scans"] for d in analytics["daily_scans"])
        assert daily_total == 3, f"Client B daily total should be 3, got {daily_total}"
        db.close()


# =====================================================================
# TEST: Missing assignment history safety
# =====================================================================

class TestMissingAssignmentSafety:

    def test_scan_with_no_assignment_attributed_to_none(self):
        """A scan that occurs before any assignment should not be attributed."""
        db = get_db_session()
        # Create a QR with a scan before its first assignment
        qr = QRCode(
            qr_id="QR-ORPHAN",
            token="tok_orphan",
            status=QRStatus.UNASSIGNED,
            created_at=datetime(2026, 1, 1),
        )
        db.add(qr)
        db.commit()
        scan = QRScanEvent(
            qr_code_id=qr.id,
            scanned_at=datetime(2026, 1, 1, 5, 0, 0),
            result_type="redirect",
        )
        db.add(scan)
        db.commit()

        owner = _attribute_scan_to_client(db, scan)
        assert owner is None, f"Orphan scan should attribute to None, got {owner}"

        # This scan should not appear for any client
        all_clients = get_distinct_client_names(db)
        for c in all_clients:
            scans = _get_historical_scan_attribution(db, c)
            scan_ids = [s.id for s in scans]
            assert scan.id not in scan_ids, \
                f"Orphan scan should not appear for client {c}"

        # Cleanup
        db.delete(scan)
        db.delete(qr)
        db.commit()
        db.close()

    def test_nonexistent_client_returns_zero(self):
        db = get_db_session()
        count = _count_historical_scans(db, "Totally Fake Client")
        assert count == 0
        db.close()


# =====================================================================
# TEST: Historical attribution edge cases (Phase 4.4 requirements)
# =====================================================================

class TestHistoricalAttributionEdgeCases:
    """
    Exhaustive boundary and edge-case testing:
    - Scan before assignment
    - Scan during assignment
    - Scan exactly at deactivation time
    - Scan exactly at next assignment time
    - QR transferred between two clients
    - Missing assignment history
    - Overlapping assignment intervals (ambiguous history reported as unattributed)
    - Multiple assignments for the same QR
    """

    def test_scan_before_assignment_returns_none(self):
        db = get_db_session()
        qr = QRCode(qr_id="QR-EDGE-1", token="tok_edge_1", status=QRStatus.ACTIVE)
        db.add(qr)
        db.commit()
        # Assignment begins at 2026-06-01 12:00:00
        a = QRAssignment(
            qr_code_id=qr.id,
            business_name="Edge Client Alpha",
            destination_url="https://alpha.example.com",
            assigned_by=1,
            assigned_at=datetime(2026, 6, 1, 12, 0, 0),
        )
        # Scan occurred earlier at 2026-06-01 11:59:59
        scan = QRScanEvent(
            qr_code_id=qr.id,
            scanned_at=datetime(2026, 6, 1, 11, 59, 59),
            result_type="redirect",
        )
        db.add_all([a, scan])
        db.commit()

        owner = _attribute_scan_to_client(db, scan)
        assert owner is None, f"Scan before assignment must be unattributed, got {owner}"

        # Must not be attributed to Edge Client Alpha
        alpha_scans = _get_historical_scan_attribution(db, "Edge Client Alpha", qr_code_ids=[qr.id])
        assert len(alpha_scans) == 0

        db.delete(scan); db.delete(a); db.delete(qr); db.commit(); db.close()

    def test_scan_during_assignment_attributes_correctly(self):
        db = get_db_session()
        qr = QRCode(qr_id="QR-EDGE-2", token="tok_edge_2", status=QRStatus.ACTIVE)
        db.add(qr)
        db.commit()
        a = QRAssignment(
            qr_code_id=qr.id,
            business_name="Edge Client Beta",
            destination_url="https://beta.example.com",
            assigned_by=1,
            assigned_at=datetime(2026, 6, 1, 10, 0, 0),
            deactivated_at=datetime(2026, 6, 1, 18, 0, 0),
        )
        scan = QRScanEvent(
            qr_code_id=qr.id,
            scanned_at=datetime(2026, 6, 1, 14, 0, 0),
            result_type="redirect",
        )
        db.add_all([a, scan])
        db.commit()

        owner = _attribute_scan_to_client(db, scan)
        assert owner == "Edge Client Beta"

        db.delete(scan); db.delete(a); db.delete(qr); db.commit(); db.close()

    def test_scan_exactly_at_deactivation_time_without_next_assignment(self):
        """A scan occurring at the exact deactivation timestamp belongs to that client."""
        db = get_db_session()
        t_deact = datetime(2026, 6, 1, 15, 30, 0)
        qr = QRCode(qr_id="QR-EDGE-3", token="tok_edge_3", status=QRStatus.DISABLED)
        db.add(qr)
        db.commit()
        a = QRAssignment(
            qr_code_id=qr.id,
            business_name="Edge Client Gamma",
            destination_url="https://gamma.example.com",
            assigned_by=1,
            assigned_at=datetime(2026, 6, 1, 10, 0, 0),
            deactivated_at=t_deact,
        )
        scan_at_deact = QRScanEvent(
            qr_code_id=qr.id,
            scanned_at=t_deact,
            result_type="redirect",
        )
        scan_after_deact = QRScanEvent(
            qr_code_id=qr.id,
            scanned_at=datetime(2026, 6, 1, 15, 30, 1),
            result_type="redirect",
        )
        db.add_all([a, scan_at_deact, scan_after_deact])
        db.commit()

        owner_at = _attribute_scan_to_client(db, scan_at_deact)
        assert owner_at == "Edge Client Gamma", f"Scan at deactivation time should attribute to Gamma, got {owner_at}"

        owner_after = _attribute_scan_to_client(db, scan_after_deact)
        assert owner_after is None, f"Scan after deactivation must be unattributed, got {owner_after}"

        db.delete(scan_at_deact); db.delete(scan_after_deact); db.delete(a); db.delete(qr); db.commit(); db.close()

    def test_scan_exactly_at_next_assignment_time_transfers_cleanly(self):
        """When QR is transferred at T_transfer, a scan at T_transfer belongs to the new client."""
        db = get_db_session()
        t_transfer = datetime(2026, 6, 1, 12, 0, 0)
        qr = QRCode(qr_id="QR-EDGE-4", token="tok_edge_4", status=QRStatus.ACTIVE)
        db.add(qr)
        db.commit()

        a1 = QRAssignment(
            qr_code_id=qr.id,
            business_name="Old Owner",
            destination_url="https://old.example.com",
            assigned_by=1,
            is_active=False,
            assigned_at=datetime(2026, 6, 1, 8, 0, 0),
            deactivated_at=t_transfer,
        )
        a2 = QRAssignment(
            qr_code_id=qr.id,
            business_name="New Owner",
            destination_url="https://new.example.com",
            assigned_by=1,
            is_active=True,
            assigned_at=t_transfer,
        )
        # Scan at exact moment of transfer
        scan_exact = QRScanEvent(
            qr_code_id=qr.id,
            scanned_at=t_transfer,
            result_type="redirect",
        )
        # Scan 1 second before transfer
        scan_before = QRScanEvent(
            qr_code_id=qr.id,
            scanned_at=datetime(2026, 6, 1, 11, 59, 59),
            result_type="redirect",
        )
        db.add_all([a1, a2, scan_exact, scan_before])
        db.commit()

        assert _attribute_scan_to_client(db, scan_before) == "Old Owner"
        assert _attribute_scan_to_client(db, scan_exact) == "New Owner"

        db.delete(scan_exact); db.delete(scan_before); db.delete(a2); db.delete(a1); db.delete(qr); db.commit(); db.close()

    def test_overlapping_assignments_different_clients_reported_unattributed(self):
        """Ambiguous/corrupted overlapping assignments between different clients must return None and never double count."""
        db = get_db_session()
        qr = QRCode(qr_id="QR-EDGE-5", token="tok_edge_5", status=QRStatus.ACTIVE)
        db.add(qr)
        db.commit()

        # Both assignments historical with overlapping date intervals for the same QR
        a1 = QRAssignment(
            qr_code_id=qr.id,
            business_name="Client Conflicting A",
            destination_url="https://conflicta.example.com",
            assigned_by=1,
            is_active=False,
            assigned_at=datetime(2026, 6, 1, 10, 0, 0),
            deactivated_at=datetime(2026, 6, 1, 20, 0, 0),
        )
        a2 = QRAssignment(
            qr_code_id=qr.id,
            business_name="Client Conflicting B",
            destination_url="https://conflictb.example.com",
            assigned_by=1,
            is_active=False,
            assigned_at=datetime(2026, 6, 1, 10, 0, 0),
            deactivated_at=datetime(2026, 6, 1, 20, 0, 0),
        )
        scan = QRScanEvent(
            qr_code_id=qr.id,
            scanned_at=datetime(2026, 6, 1, 15, 0, 0),
            result_type="redirect",
        )
        db.add_all([a1, a2, scan])
        db.commit()

        owner = _attribute_scan_to_client(db, scan)
        assert owner is None, f"Ambiguous overlapping history must return None, got {owner}"

        # Neither client gets credit for this ambiguous scan
        scans_a = _get_historical_scan_attribution(db, "Client Conflicting A", qr_code_ids=[qr.id])
        scans_b = _get_historical_scan_attribution(db, "Client Conflicting B", qr_code_ids=[qr.id])
        assert len(scans_a) == 0
        assert len(scans_b) == 0

        db.delete(scan); db.delete(a2); db.delete(a1); db.delete(qr); db.commit(); db.close()

    def test_multiple_sequential_transfers_three_clients(self):
        """A QR transferred across 3 clients: Client 1 -> Client 2 -> Client 3."""
        db = get_db_session()
        qr = QRCode(qr_id="QR-EDGE-6", token="tok_edge_6", status=QRStatus.ACTIVE)
        db.add(qr)
        db.commit()

        a1 = QRAssignment(
            qr_code_id=qr.id,
            business_name="Client Triple 1",
            destination_url="https://c1.example.com",
            assigned_by=1,
            is_active=False,
            assigned_at=datetime(2026, 1, 1),
            deactivated_at=datetime(2026, 2, 1),
        )
        a2 = QRAssignment(
            qr_code_id=qr.id,
            business_name="Client Triple 2",
            destination_url="https://c2.example.com",
            assigned_by=1,
            is_active=False,
            assigned_at=datetime(2026, 2, 1),
            deactivated_at=datetime(2026, 3, 1),
        )
        a3 = QRAssignment(
            qr_code_id=qr.id,
            business_name="Client Triple 3",
            destination_url="https://c3.example.com",
            assigned_by=1,
            is_active=True,
            assigned_at=datetime(2026, 3, 1),
        )
        s1 = QRScanEvent(qr_code_id=qr.id, scanned_at=datetime(2026, 1, 15), result_type="redirect")
        s2 = QRScanEvent(qr_code_id=qr.id, scanned_at=datetime(2026, 2, 15), result_type="redirect")
        s3 = QRScanEvent(qr_code_id=qr.id, scanned_at=datetime(2026, 3, 15), result_type="redirect")

        db.add_all([a1, a2, a3, s1, s2, s3])
        db.commit()

        assert _attribute_scan_to_client(db, s1) == "Client Triple 1"
        assert _attribute_scan_to_client(db, s2) == "Client Triple 2"
        assert _attribute_scan_to_client(db, s3) == "Client Triple 3"

        assert _count_historical_scans(db, "Client Triple 1", qr_code_ids=[qr.id]) == 1
        assert _count_historical_scans(db, "Client Triple 2", qr_code_ids=[qr.id]) == 1
        assert _count_historical_scans(db, "Client Triple 3", qr_code_ids=[qr.id]) == 1

        db.delete(s1); db.delete(s2); db.delete(s3)
        db.delete(a3); db.delete(a2); db.delete(a1); db.delete(qr)
        db.commit(); db.close()


# =====================================================================
# TEST: API endpoints via HTTP (integration)
# =====================================================================

class TestClientAPIEndpoints:

    def _get_token(self):
        resp = client.post("/api/auth/login", json={
            "username": "admin",
            "password": "admin123",
        })
        return resp.json()["access_token"]

    def test_clients_overview_api(self):
        token = self._get_token()
        resp = client.get("/api/clients/overview", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert "total_clients" in data
        assert data["total_clients"] >= 3

    def test_clients_list_api(self):
        token = self._get_token()
        resp = client.get("/api/clients", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        clients_map = {item["client_name"]: item for item in data["items"]}
        assert "Client A" in clients_map
        assert clients_map["Client A"]["total_scans"] == 3
        assert clients_map["Client B"]["total_scans"] == 3
        assert clients_map["Client C"]["total_scans"] == 2

    def test_client_detail_api(self):
        token = self._get_token()
        resp = client.get("/api/clients/Client%20B", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_scans"] == 3
        assert data["total_qr_codes"] == 2

    def test_client_analytics_api(self):
        token = self._get_token()
        resp = client.get(
            "/api/clients/Client%20A/analytics?days=365",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        daily_total = sum(d["scans"] for d in data["daily_scans"])
        assert daily_total == 3

