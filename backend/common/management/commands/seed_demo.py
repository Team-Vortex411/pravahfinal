from datetime import timedelta

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import Department, User
from ai import orchestrator
from applications.models import Application
from common.audit import notify
from documents.models import Document
from documents.services import apply_expiry_state
from embeddings.services import upsert_problem_embedding, upsert_startup_embedding
from evaluations.models import Evaluation
from pilots.models import Contract, KPI, Milestone, Pilot
from problem_statements.models import ProblemStatement
from recommendations.models import Recommendation
from reports.models import FinalReport, WeeklyKPIResult, WeeklyReport
from startups.models import Startup
from storage.pdf import render_pdf
from storage.services import put_bytes


TODAY = timezone.localdate()


class Command(BaseCommand):
    help = "Reset and seed the PRAVAH demonstration workspace."

    def handle(self, *args, **options):
        if not settings.DEMO_MODE:
            raise CommandError("Refusing to seed because DEMO_MODE is not true.")
        call_command("flush", "--no-input")
        self.users = {}
        self.deps = {}
        self.problems = {}
        self.startups = {}
        self._departments()
        self._users()
        self._problems()
        self._startups()
        self._documents()
        self._completed_and_active()
        self._open_cases()
        self._filler_applications()
        self._notify()
        self.stdout.write(self.style.SUCCESS(
            f"Seeded {ProblemStatement.objects.count()} problem statements, "
            f"{Application.objects.count()} applications, {Pilot.objects.count()} pilots."
        ))

    def _user(self, email, name, role, designation="", employee_id="", department=None):
        first, *rest = name.split()
        user = User.objects.create_user(
            username=email,
            email=email,
            password="demo123",
            first_name=first,
            last_name=" ".join(rest),
            role=role,
            designation=designation,
            employee_id=employee_id,
            department=department,
            phone="011-23000000" if role != User.Role.STARTUP else "9800000000",
        )
        self.users[email] = user
        return user

    def _departments(self):
        rows = [
            ("Health Department", "HEA", "Ministry of Health and Family Welfare"),
            ("Agriculture Department", "AGR", "Ministry of Agriculture and Farmers Welfare"),
            ("Urban Development Department", "URB", "Ministry of Housing and Urban Affairs"),
            ("Education Department", "EDU", "Ministry of Education"),
            ("Transport Department", "TRN", "Ministry of Road Transport and Highways"),
            ("Administrative Reforms", "ADM", "Department of Administrative Reforms"),
        ]
        for name, code, ministry in rows:
            self.deps[code] = Department.objects.create(name=name, code=code, ministry=ministry)

    def _users(self):
        self._user("admin@gov.in", "Meera Krishnan", User.Role.GOVERNMENT_ADMIN, "Joint Director", "IPC-014", self.deps["ADM"])
        self._user("evaluator@gov.in", "Dr. Suresh Iyer", User.Role.TECHNICAL_EVALUATOR, "Principal Technical Evaluator", "IPC-108", self.deps["HEA"])
        self._user("procurement@gov.in", "Rajesh Nair", User.Role.PROCUREMENT_OFFICER, "Procurement Officer", "IPC-221", self.deps["ADM"])
        self._user("field@gov.in", "Kavita Rao", User.Role.FIELD_EVALUATOR, "Field Evaluator", "IPC-317", self.deps["URB"])
        self._user("field2@gov.in", "Imran Qureshi", User.Role.FIELD_EVALUATOR, "Field Evaluator", "IPC-318", self.deps["HEA"])

    def _problems(self):
        evaluator = self.users["evaluator@gov.in"]
        officer = self.users["procurement@gov.in"]
        admin = self.users["admin@gov.in"]
        specs = [
            ("medicine", "PS-HEA-2026-001", "AI-Based Medicine Stock-Out Prediction", "HEA", "Maharashtra", "Healthcare AI", "PILOT_COMPLETED",
             "Predict medicine stock-outs in government hospitals before shelves run empty.",
             "A district-wide forecasting service that warns pharmacists 14 days before essential medicines stock out.",
             ["Hospital inventory integration", "Real-time stock-out prediction", "Essential medicine list coverage", "Role-based access for pharmacists"],
             "Pune and Nagpur district hospitals", 12),
            ("waste", "PS-URB-2026-002", "Smart Waste Collection Optimization", "URB", "Karnataka", "Urban IoT", "PILOT_ACTIVE",
             "Optimise municipal waste collection routes using fill-level and complaint signals.",
             "Fewer missed collections and lower fuel use without reducing ward coverage.",
             ["Bin fill sensing", "Dynamic route planning", "Ward-level dashboard", "Complaint integration"],
             "Bengaluru South zone", 10),
            ("agri", "PS-AGR-2026-003", "Agricultural Disease Detection", "AGR", "Madhya Pradesh", "Agri computer vision", "PILOT_COMPLETED",
             "Detect crop disease early enough for extension officers to advise treatment.",
             "Image-based detection for soybean and wheat with alerts in Hindi and English.",
             ["Field image diagnosis", "Extension-officer workflow", "Low-bandwidth capture", "False-positive control"],
             "Bhopal and Sehore blocks", 12),
            ("traffic", "PS-TRN-2026-004", "Traffic Congestion Prediction", "TRN", "Delhi", "Mobility analytics", "PILOT_ACTIVE",
             "Predict corridor congestion so traffic police can stage diversions earlier.",
             "A 30-minute congestion forecast for selected arterial corridors.",
             ["Corridor prediction", "Signal-timing export", "Incident overlay", "Control-room dashboard"],
             "Ring Road and Mathura Road corridors", 8),
            ("water", "PS-URB-2026-005", "Water Leakage Detection", "URB", "Odisha", "Water IoT", "PILOT_ACTIVE",
             "Locate non-revenue water losses in urban distribution lines.",
             "Detect leakage clusters in Cuttack pilot zones and confirm them in the field.",
             ["Acoustic or pressure sensing", "Zone metering", "Field work-order output", "Night-flow analysis"],
             "Cuttack municipal wards 12–18", 10),
            ("attendance", "PS-EDU-2026-006", "AI-Based School Attendance Analytics", "EDU", "Rajasthan", "Education analytics", "PILOT_ACTIVE",
             "Understand chronic absence without replacing the school register.",
             "Early warning of students at risk of chronic absence, for block education officers.",
             ["Register integration", "Absence-risk scoring", "Privacy-preserving student identifiers", "Block dashboard"],
             "Jaipur and Sikar blocks", 10),
            ("tele", "PS-HEA-2026-007", "Rural Tele-diagnostics Triage", "HEA", "Chhattisgarh", "Telehealth", "PILOT_COMPLETED",
             "Support health and wellness centres in deciding which cases need referral.",
             "A triage aid for ANMs, with a clear handoff to the medical officer.",
             ["Symptom triage", "Referral recommendation", "Offline-tolerant capture", "Audit trail"],
             "Raipur rural health and wellness centres", 12),
            ("fleet", "PS-TRN-2026-008", "Predictive Maintenance for Municipal Fleets", "TRN", "Telangana", "Fleet analytics", "PILOT_COMPLETED",
             "Reduce breakdowns of municipal service vehicles.",
             "Predict workshop interventions for buses and utility vehicles.",
             ["Telematics integration", "Breakdown prediction", "Workshop scheduling", "False-alarm control"],
             "Hyderabad municipal workshops", 12),
            ("street", "PS-URB-2026-009", "Streetlight Fault Detection", "URB", "Gujarat", "Urban IoT", "PILOT_ACTIVE",
             "Detect failed streetlights before citizen complaints accumulate.",
             "Nightly fault map for the maintenance contractor and the municipal engineer.",
             ["Feeder-level monitoring", "Fault localisation", "Crew work orders", "Outage duration tracking"],
             "Ahmedabad west zone", 8),
            ("cold", "PS-HEA-2026-010", "Cold-chain Integrity Monitoring", "HEA", "Odisha", "Healthcare IoT", "OPEN",
             "Watch vaccine cold-chain excursions between district stores and session sites.",
             "Excursion alerts with a temperature history an immunisation officer can audit.",
             ["Temperature logging", "Excursion alerts", "Store-to-session traceability", "Offline sync"],
             "Cuttack and Puri vaccine stores", 8),
            ("grievance", "PS-ADM-2026-011", "AI-Based Public Grievance Routing", "ADM", "Delhi", "Public service NLP", "OPEN",
             "Route citizen grievances to the responsible desk without losing the original text.",
             "Shorter misroute rate on a sample of CPGRAMS-style grievances.",
             ["Multilingual classification", "Desk routing", "Human override", "Audit of model suggestions"],
             "Central grievance cell sample queue", 8),
            ("triage", "PS-HEA-2026-014", "Primary-Health Centre Referral Triage", "HEA", "Odisha", "Telehealth", "OPEN",
             "Help primary health centres decide which fever and maternal cases need same-day referral, without replacing the medical officer.",
             "A reasoned referral suggestion with an audit trail for the medical officer.",
             ["Symptom triage", "Referral recommendation", "Audit trail", "Low-bandwidth capture"],
             "Cuttack primary health centres", 8),
            ("indent", "PS-HEA-2026-013", "Hospital Indent and Expiry Forecasting", "HEA", "Maharashtra", "Healthcare AI", "OPEN",
             "Forecast district-hospital indents and expiring medicine batches before they are wasted or stock out.",
             "A pharmacist-facing forecast of essential medicine demand and expiry risk across a hospital store.",
             ["Hospital inventory integration", "Expiry-risk prediction", "Essential medicine coverage", "Pharmacist workflow"],
             "Pune municipal hospitals", 8),
            ("drone", "PS-URB-2026-012", "Drone-based Encroachment Detection", "URB", "Maharashtra", "Geospatial imaging", "OPEN",
             "Compare drone imagery with revenue maps to flag possible encroachments for a human surveyor.",
             "A review queue for the municipal estate officer. The model must not itself declare an encroachment.",
             ["Orthomosaic comparison", "Human review queue", "Change highlighting", "No automatic penalty"],
             "Pimpri-Chinchwad sample wards", 8),
        ]
        for key, code, title, dep, location, domain, status, description, outcome, reqs, pilot_location, weeks in specs:
            ps = ProblemStatement.objects.create(
                code=code,
                title=title,
                description=description,
                department=self.deps[dep],
                location=location,
                technology_domain=domain,
                expected_outcome=outcome,
                technical_requirements=reqs,
                eligibility_criteria=[
                    "DPIIT-recognised startup",
                    "Valid GST registration",
                    "Ability to deploy at the stated pilot location",
                    "Willingness to accept field verification of reported results",
                ],
                required_documents=["DPIIT", "GST", "PAN", "INCORPORATION", "TECHNICAL_PROPOSAL"],
                application_deadline=TODAY + timedelta(days=21 if status == "OPEN" else -5),
                pilot_joining_deadline=TODAY + timedelta(days=40 if status == "OPEN" else -2),
                pilot_location=pilot_location,
                pilot_duration_weeks=weeks,
                status=status,
                technical_evaluator=evaluator,
                procurement_officer=officer,
                created_by=admin,
            )
            if key == "grievance":
                ProblemStatement.objects.filter(id=ps.id).update(created_at=timezone.now() - timedelta(days=48))
                ps.refresh_from_db()
            upsert_problem_embedding(ps)
            self.problems[key] = ps

    def _startup(self, email, contact, company, domain, technologies, city, state, years, team, description, capabilities, experience, dpiit, gstin):
        user = self._user(email, contact, User.Role.STARTUP)
        startup = Startup.objects.create(
            user=user,
            company_name=company,
            domain=domain,
            technologies=technologies,
            dpiit_number=dpiit,
            gstin=gstin,
            city=city,
            state=state,
            experience_years=years,
            team_size=team,
            description=description,
            capabilities=capabilities,
            relevant_experience=experience,
            contact_person=contact,
        )
        upsert_startup_embedding(startup)
        self.startups[company] = startup
        return startup

    def _startups(self):
        self._startup(
            "nova@novatech.in", "Arjun Malhotra", "NovaTech", "Healthcare AI",
            "Machine learning, hospital inventory forecasting, demand sensing, pharmacist workflow",
            "Pune", "Maharashtra", 6, 28,
            "Machine-learning platform for forecasting hospital medicine demand and preventing inventory shortages.",
            "Time-series forecasting, HIS integration, essential-medicine watchlists, and pharmacist alerts.",
            "Deployed inventory forecasting for two state medical colleges and a municipal hospital network.",
            "DIPP184422", "27AABCU9603R1ZM",
        )
        self._startup(
            "agro@agroai.in", "Ananya Joshi", "AgroAI", "AgriTech",
            "Computer vision, crop disease detection, offline mobile capture, Hindi advisory",
            "Bhopal", "Madhya Pradesh", 5, 22,
            "Computer-vision platform that identifies crop disease from field photographs and briefs extension officers.",
            "On-device capture, disease library for soybean and wheat, and officer review before any advisory is sent.",
            "Worked with a state agriculture university on soybean rust detection across two kharif seasons.",
            "DIPP992011", "23AAGCA1122P1ZV",
        )
        self._startup(
            "med@medpredict.in", "Dr. Farhan Ali", "MedPredict", "Telehealth",
            "Clinical triage, referral support, offline forms, audit trail",
            "Raipur", "Chhattisgarh", 7, 18,
            "Triage support for rural health and wellness centres, designed to assist and not replace the medical officer.",
            "Symptom capture, referral suggestion with reasons, and a full audit trail of overrides.",
            "Piloted an ANM decision aid in two blocks under a medical college ethics review.",
            "DIPP441908", "22AABCM4419Q1Z8",
        )
        self._startup(
            "ops@smartops.in", "Neha Kulkarni", "SmartOps", "Fleet analytics",
            "Telematics, predictive maintenance, workshop scheduling",
            "Hyderabad", "Telangana", 4, 16,
            "Predictive maintenance for public vehicle fleets using telematics and workshop history.",
            "Failure-risk scores, workshop slot suggestions, and false-alarm review.",
            "Ran a depot pilot for a municipal bus operator. Breakdown reduction was below the contracted target.",
            "DIPP220194", "36AASCS2201D1Z2",
        )
        self._startup(
            "waste@wasteflow.in", "Rohan Desai", "WasteFlow", "Urban sanitation",
            "IoT bin sensors, route optimisation, ward dashboards",
            "Bengaluru", "Karnataka", 4, 19,
            "Fill-level sensing and dynamic waste collection routing for municipal wards.",
            "Sensor retrofit, route engine, and a ward dashboard for the health inspector.",
            "Optimised collections for a cantonment board before this municipal pilot.",
            "DIPP771245", "29AABCW7712E1ZX",
        )
        self._startup(
            "aqua@aquasense.in", "Smita Behera", "AquaSense", "Water IoT",
            "Acoustic leak detection, pressure sensors, zone metering, work orders",
            "Cuttack", "Odisha", 5, 14,
            "Leakage detection for urban water networks using night flow, pressure and acoustic sensing.",
            "Zone meters, suspected-leak clustering, and field work orders for the municipal water section.",
            "Mapped non-revenue water in a coastal town distribution zone.",
            "DIPP318800", "21AABCA3188F1Z1",
        )
        self._startup(
            "edu@edutrack.in", "Vikram Singh", "EduTrack", "Education analytics",
            "Attendance analytics, early-warning scores, privacy-preserving identifiers",
            "Jaipur", "Rajasthan", 6, 15,
            "Early-warning analytics for chronic school absence, built to sit beside the existing register.",
            "Register import, risk scores for block officers, and no public ranking of children.",
            "Supported a district education office on attendance data quality for two academic years.",
            "DIPP650332", "08AABCE6503G1Z4",
        )
        self._startup(
            "path@pathfind.in", "Aisha Khan", "PathFind", "Mobility analytics",
            "Congestion forecasting, corridor models, control-room dashboards",
            "New Delhi", "Delhi", 5, 21,
            "Short-horizon congestion prediction for urban arterials and traffic police control rooms.",
            "Corridor models, incident overlay, and an export for signal-timing review.",
            "Provided festival-period congestion briefs to a city traffic police unit.",
            "DIPP104488", "07AABCP1044H1Z9",
        )
        self._startup(
            "grid@ujjwalgrid.in", "Harpreet Singh", "UjjwalGrid", "Urban energy IoT",
            "Feeder monitoring, streetlight fault detection, crew dispatch",
            "Ahmedabad", "Gujarat", 4, 12,
            "Feeder and pole monitoring that flags streetlight faults before complaint volume rises.",
            "Nightly fault maps, outage duration, and crew work orders.",
            "Monitored a municipal lighting feeder in a smart-city pilot ward.",
            "DIPP880123", "24AABCU8801J1Z3",
        )
        self._startup(
            "cold@sheetal.in", "Manish Gupta", "SheetalCold", "Healthcare IoT",
            "Temperature logging, cold-chain alerts, offline sync",
            "Bhubaneswar", "Odisha", 3, 11,
            "Temperature loggers and excursion alerts for vaccine stores and session-site carriers.",
            "Device provisioning, excursion workflow, and store-to-session traceability.",
            "Logged temperatures for a district vaccine store during a pulse immunisation round.",
            "DIPP552019", "21AABCS5520K1Z6",
        )
        self._startup(
            "sky@bharatsky.in", "Leela Menon", "BharatSky", "Geospatial imaging",
            "Drone survey, orthomosaic comparison, human review tools",
            "Pune", "Maharashtra", 4, 13,
            "Drone imagery comparison that highlights possible change for a human surveyor. It does not issue penalties.",
            "Flight planning, change highlighting, and a review queue for the estate officer.",
            "Flew a municipal mapping sortie. Field access was later withdrawn and the pilot was cancelled.",
            "DIPP229910", "27AABCB2299L1Z0",
        )
        fillers = [
            ("BharatMed", "Healthcare AI", "Pune", "Maharashtra"),
            ("GramSetu", "AgriTech", "Indore", "Madhya Pradesh"),
            ("NadiTech", "Water IoT", "Bhubaneswar", "Odisha"),
            ("KisanLens", "AgriTech", "Jabalpur", "Madhya Pradesh"),
            ("CityPulse", "Mobility analytics", "Delhi", "Delhi"),
            ("ShikshaPath", "Education analytics", "Ajmer", "Rajasthan"),
            ("NirmalCity", "Urban sanitation", "Mysuru", "Karnataka"),
            ("AarogyaNode", "Telehealth", "Bilaspur", "Chhattisgarh"),
            ("FleetMind", "Fleet analytics", "Warangal", "Telangana"),
            ("LekhaAI", "Public service NLP", "Delhi", "Delhi"),
            ("DawaWatch", "Healthcare AI", "Nagpur", "Maharashtra"),
            ("JalDhara", "Water IoT", "Cuttack", "Odisha"),
        ]
        for i, (name, domain, city, state) in enumerate(fillers, start=1):
            self._startup(
                f"founder{i}@demo.in", f"Founder {name}", name, domain,
                domain, city, state, 2, 8,
                f"{name} is a DPIIT-recognised startup working on {domain.lower()} for public agencies.",
                f"Prototype capability in {domain.lower()}.",
                "Limited government pilot experience. Included so the evaluation queue is realistic.",
                f"DIPP70{i:04d}", f"29AABCX{i:04d}Z1",
            )

    def _pdf(self, title, lines, filename):
        return put_bytes(render_pdf(title, lines, subtitle="Demonstration file · not a statutory certificate"), filename, prefix="demo")

    def _doc(self, startup, doc_type, name, status, expiry=None, no_expiry=False, application=None, pilot=None, lines=None):
        key = self._pdf(name, lines or [name, startup.company_name, f"Status seed: {status}"], f"{doc_type}.pdf")
        doc = Document.objects.create(
            startup=startup,
            application=application,
            pilot=pilot,
            name=name,
            document_type=doc_type,
            object_key=key,
            file_name=f"{doc_type.lower()}.pdf",
            content_type="application/pdf",
            size_bytes=2048,
            verification_status=status,
            verified_by=self.users["evaluator@gov.in"] if status != Document.Verification.PENDING_VERIFICATION else None,
            verified_date=TODAY - timedelta(days=40) if status != Document.Verification.PENDING_VERIFICATION else None,
            expiry_date=expiry,
            no_expiry=no_expiry,
            currently_valid=status in {Document.Verification.VERIFIED_VALID, Document.Verification.EXPIRING_SOON},
        )
        if status in {Document.Verification.VERIFIED_VALID, Document.Verification.EXPIRING_SOON, Document.Verification.EXPIRED}:
            apply_expiry_state(doc)
        return doc

    def _documents(self):
        nova = self.startups["NovaTech"]
        self._doc(nova, "DPIIT", "DPIIT recognition — NovaTech", "VERIFIED_VALID", no_expiry=True)
        self._doc(nova, "GST", "GST certificate — NovaTech", "VERIFIED_VALID", expiry=TODAY + timedelta(days=180))
        self._doc(nova, "ISO_27001", "ISO 27001 — NovaTech", "EXPIRING_SOON", expiry=TODAY + timedelta(days=18))
        self._doc(nova, "ISO_9001", "ISO 9001 — NovaTech", "EXPIRED", expiry=TODAY - timedelta(days=45))
        self._doc(nova, "PAN", "PAN — NovaTech", "VERIFIED_VALID", no_expiry=True)
        self._doc(nova, "INCORPORATION", "Certificate of incorporation — NovaTech", "VERIFIED_VALID", no_expiry=True)
        expiring = [
            ("AgroAI", "ISO_9001", 12),
            ("MedPredict", "ISO_27001", 9),
            ("WasteFlow", "GST", 21),
            ("AquaSense", "ISO_9001", 6),
            ("EduTrack", "GST", 15),
        ]
        for company, dtype, days in expiring:
            self._doc(self.startups[company], dtype, f"{dtype} — {company}", "EXPIRING_SOON", expiry=TODAY + timedelta(days=days))
        for company in ["AgroAI", "MedPredict", "SmartOps", "WasteFlow", "AquaSense", "EduTrack", "PathFind", "UjjwalGrid", "SheetalCold", "BharatSky"]:
            startup = self.startups[company]
            self._doc(startup, "DPIIT", f"DPIIT recognition — {company}", "VERIFIED_VALID", no_expiry=True)
            self._doc(startup, "PAN", f"PAN — {company}", "VERIFIED_VALID", no_expiry=True)
            self._doc(startup, "INCORPORATION", f"Incorporation — {company}", "VERIFIED_VALID", no_expiry=True)
            if company != "AquaSense":
                self._doc(startup, "GST", f"GST — {company}", "VERIFIED_VALID", expiry=TODAY + timedelta(days=200))
        self._doc(self.startups["SheetalCold"], "GST", "GST — SheetalCold", "PENDING_VERIFICATION")
        self._doc(self.startups["BharatMed"], "DPIIT", "DPIIT — BharatMed", "PENDING_VERIFICATION")
        self._doc(self.startups["LekhaAI"], "GST", "GST — LekhaAI", "REJECTED", lines=["GST image was illegible. Please upload a clearer copy."])

    def _application(self, startup, problem_key, status, readiness="YES", proposal="", reason=""):
        ps = self.problems[problem_key]
        app = Application.objects.create(
            code=f"APP-2026-{Application.objects.count() + 1:04d}",
            startup=startup,
            problem_statement=ps,
            status=status,
            eligibility_confirmed=readiness == "YES",
            eligibility_checks={"DPIIT-recognised startup": True, "Valid GST registration": True},
            pilot_readiness=readiness,
            proposal_text=proposal,
            rejection_reason=reason,
        )
        if proposal:
            result = orchestrator.analyze_proposal(
                {
                    "title": ps.title,
                    "department": ps.department.name,
                    "description": ps.description,
                    "technical_requirements": ps.technical_requirements,
                    "expected_outcome": ps.expected_outcome,
                },
                {
                    "company_name": startup.company_name,
                    "domain": startup.domain,
                    "technologies": startup.technologies,
                    "description": startup.description,
                    "relevant_experience": startup.relevant_experience,
                    "capabilities": startup.capabilities,
                },
                proposal,
                "DPIIT, GST, PAN on file",
            )
            app.ai_analysis = result
            app.save(update_fields=["ai_analysis"])
        return app

    def _eval(self, app, scores, decision, comments):
        Evaluation.objects.create(
            application=app,
            evaluator=self.users["evaluator@gov.in"],
            scores=scores,
            comments=comments,
            decision=decision,
            decided_at=timezone.now() - timedelta(days=20),
        )

    def _pilot(self, app, status, start, end, location, kpis, milestones, weeks, final_actuals=None, choice="", officer_note="", complaint=None, late_week=None, clarify_week=None):
        pilot = Pilot.objects.create(
            code=f"PIL-2026-{Pilot.objects.count() + 1:04d}",
            application=app,
            startup=app.startup,
            problem_statement=app.problem_statement,
            procurement_officer=self.users["procurement@gov.in"],
            field_evaluator=self.users["field@gov.in"],
            location=location,
            start_date=start,
            end_date=end,
            joining_deadline=start - timedelta(days=7),
            duration_weeks=max(8, (end - start).days // 7),
            responsibilities="Deploy the stated solution, train the nodal officer, submit weekly evidence, and attend field verification.",
            government_support="Site access, a nodal officer, and anonymised operational data required for the pilot. No procurement commitment.",
            payment_conditions="Milestone payments are conditional on field verification. They are not a scale-up award.",
            reporting_frequency="Weekly",
            security_requirements="No patient, student or citizen identifier leaves the pilot environment without the nodal officer's written clearance.",
            status=status,
            kpi_locked=status in {Pilot.Status.ACTIVE, Pilot.Status.COMPLETED, Pilot.Status.CANCELLED},
        )
        contract = Contract.objects.create(
            pilot=pilot,
            contract_no=f"PRAVAH/PC/2026/{pilot.id:04d}",
            status=Contract.Status.CONTRACT_ACCEPTED if status != Pilot.Status.CONTRACT_PENDING else Contract.Status.SENT,
            kpi_method=Contract.KPIMethod.MANUAL,
            kpis_finalized=True,
            sent_at=timezone.now() - timedelta(days=80),
            accepted_at=timezone.now() - timedelta(days=70) if status != Pilot.Status.CONTRACT_PENDING else None,
        )
        for order, (name, amount, due, mstatus) in enumerate(milestones, start=1):
            Milestone.objects.create(pilot=pilot, name=name, amount=amount, due_week=due, status=mstatus, order=order)
        for order, spec in enumerate(kpis, start=1):
            KPI.objects.create(
                pilot=pilot,
                name=spec["name"],
                target=spec["target"],
                unit=spec["unit"],
                weight=spec["weight"],
                priority=spec["priority"],
                direction=spec["direction"],
                max_score=spec.get("max_score", 120),
                source="MANUAL",
                order=order,
            )
        from pilots.services import write_unsigned_contract

        write_unsigned_contract(pilot)
        if status != Pilot.Status.CONTRACT_PENDING:
            signed = self._pdf(f"Signed {contract.contract_no}", [f"Signed by {app.startup.company_name}", contract.body_text[:400]], "signed-contract.pdf")
            contract.signed_key = signed
            contract.unsigned_key = ""
            contract.replacement_log = [{"at": timezone.now().isoformat(), "event": "Unsigned contract replaced by signed contract during demonstration seed."}]
            contract.save()
        current_week = weeks
        for week in range(1, current_week + 1):
            due = start + timedelta(days=7 * week)
            claims = []
            for spec in kpis:
                series = spec.get("weekly") or []
                if week - 1 < len(series):
                    claims.append({"name": spec["name"], "actual": series[week - 1], "unit": spec["unit"], "evidence_ref": f"Week {week} field sheet"})
            late = late_week == week
            clarify = clarify_week == week
            if late:
                due = TODAY - timedelta(days=2)
            report_status = WeeklyReport.Status.VERIFIED
            verification = "VERIFIED"
            if late:
                report_status = WeeklyReport.Status.LATE
                verification = ""
            elif clarify:
                report_status = WeeklyReport.Status.NEEDS_CLARIFICATION
                verification = "NEEDS_CLARIFICATION"
            report = WeeklyReport.objects.create(
                pilot=pilot,
                week=week,
                narrative=self._week_narrative(app.startup.company_name, week, claims),
                comments="Submitted through the PRAVAH weekly form.",
                kpi_claims=claims,
                due_date=due,
                submitted_at=None if late else timezone.now() - timedelta(days=3),
                status=report_status,
                verification_status=verification,
                verified_by=None if late or clarify else self.users["field@gov.in"],
                verified_at=None if late or clarify else timezone.now() - timedelta(days=2),
                observations="" if not clarify else "Field visit could not confirm the sensor count stated in the report. Please resubmit the ward sheet.",
                delay_reason="Vehicle breakdown delayed the ward round. The inspection sheet is attached as an excuse." if late else "",
                delay_review="PENDING" if late else "",
            )
            if report.verification_status == "VERIFIED":
                for claim in claims:
                    kpi = pilot.kpis.get(name=claim["name"])
                    WeeklyKPIResult.objects.create(report=report, kpi=kpi, actual=claim["actual"], unit=claim["unit"], evidence_ref=claim["evidence_ref"], note="Stored after field verification")
                report.ai_progress = {
                    "demo": True,
                    "notice": "AI service unavailable. Showing demo analysis so the prototype remains functional.",
                    "result": {
                        "progress_summary": f"Verified week {week} values are on file for {app.startup.company_name}. This note is advisory.",
                        "trend": "improving",
                        "improving": [claims[0]["name"]] if claims else [],
                        "declining": [],
                        "concern": "No declining verified KPI in this seeded week.",
                        "improvement_tip": "Keep the field sheet attached to every weekly claim so the evaluator can verify the figure.",
                    },
                }
                report.save(update_fields=["ai_progress"])
        if final_actuals and status == Pilot.Status.COMPLETED:
            FinalReport.objects.create(
                pilot=pilot,
                narrative=f"{app.startup.company_name} submitted the closing field report for {app.problem_statement.title}. Figures below were verified by the field evaluator before scoring.",
                kpi_claims=[{"name": k, "actual": v, "unit": next(s["unit"] for s in kpis if s["name"] == k)} for k, v in final_actuals.items()],
                submitted_at=timezone.now() - timedelta(days=12),
                verification_status="VERIFIED",
                verified_by=self.users["field@gov.in"],
                verified_at=timezone.now() - timedelta(days=8),
                observations="Field sample checked against source registers. Verified values, not startup claims, were released for scoring.",
                extracted_kpis=[{"name": k, "actual": v, "unit": next(s["unit"] for s in kpis if s["name"] == k)} for k, v in final_actuals.items()],
                extraction_demo=True,
                ai_analysis={
                    "demo": True,
                    "notice": "AI service unavailable. Showing demo analysis so the prototype remains functional.",
                    "result": {"achievement_summary": "Interpretation uses stored verified KPI values only."},
                },
            )
            from common.present import official_score

            pilot.score_cache = official_score(pilot) or {}
            pilot.save(update_fields=["score_cache"])
            if choice:
                Recommendation.objects.create(
                    pilot=pilot,
                    choice=choice,
                    officer_note=officer_note,
                    narrative="Advisory note for the competent authority. This is not a procurement order.",
                    scaleup_tips={"recommended_focus": ["Read MUST HAVE gaps before optional KPIs."], "scaleup_considerations": ["Field verification is on file."], "cautions": []},
                    evidence_report="VERIFIED FACTS are the score, milestones, complaints and field verification. AI INTERPRETATION must not be treated as a new measurement.",
                    evidence_links=[{"claim": "Overall score", "source": "Deterministic scoring engine"}],
                    recorded_by=self.users["procurement@gov.in"],
                    ai_demo=True,
                    ai_notice="AI service unavailable. Showing demo analysis so the prototype remains functional.",
                )
        if complaint:
            from complaints.models import Complaint

            Complaint.objects.create(pilot=pilot, raised_by=self.users["field@gov.in"], category=complaint[0], description=complaint[1], status=complaint[2], startup_response=complaint[3] if len(complaint) > 3 else "", officer_action=complaint[4] if len(complaint) > 4 else "")
        return pilot

    def _week_narrative(self, company, week, claims):
        bits = ", ".join(f"{c['name']} {c['actual']} {c['unit']}" for c in claims)
        return f"Week {week} field note from {company}. Reported figures: {bits}. Evidence is the ward or facility sheet for this week. These figures are not official until the field evaluator verifies them."

    def _completed_and_active(self):
        nova = self._application(
            self.startups["NovaTech"], "medicine", Application.Status.PILOT_COMPLETED,
            proposal="NovaTech will forecast hospital medicine demand from dispensing and indent history, integrate with the hospital store, and raise a real-time stock-out warning to the pharmacist. Security uses role-based access. The model was calibrated on two medical-college stores.",
        )
        self._eval(nova, {"technical_feasibility": 8, "innovation": 7, "problem_relevance": 9, "scalability": 7, "technical_capability": 8, "relevant_experience": 8}, "APPROVE_FOR_PILOT", "Feasible for a bounded hospital pilot. Security detail was adequate for pilot, not for state-wide rollout.")
        self._pilot(
            nova, Pilot.Status.COMPLETED, TODAY - timedelta(days=110), TODAY - timedelta(days=26),
            "Pune district hospitals",
            [
                {"name": "Prediction accuracy", "target": 90, "unit": "percent", "weight": 40, "priority": "MUST_HAVE", "direction": "HIGHER_IS_BETTER", "weekly": [81, 84, 87, 89, 92, 94, 95, 96]},
                {"name": "System uptime", "target": 99, "unit": "percent", "weight": 25, "priority": "MUST_HAVE", "direction": "HIGHER_IS_BETTER", "weekly": [97.5, 98.1, 98.6, 99.0, 99.1, 99.2, 99.3, 99.4]},
                {"name": "Response time", "target": 2, "unit": "seconds", "weight": 20, "priority": "BETTER_TO_HAVE", "direction": "LOWER_IS_BETTER", "weekly": [2.6, 2.4, 2.2, 2.1, 1.9, 1.8, 1.75, 1.7]},
                {"name": "Stock-out reduction", "target": 35, "unit": "percent", "weight": 15, "priority": "NICE_TO_HAVE", "direction": "HIGHER_IS_BETTER", "weekly": [18, 22, 26, 29, 32, 34, 36, 38]},
            ],
            [("Prototype ready", 400000, 2, "COMPLETE"), ("Integration complete", 600000, 5, "COMPLETE"), ("Pilot complete", 500000, 8, "COMPLETE"), ("Validation complete", 300000, 12, "COMPLETE")],
            8,
            {"Prediction accuracy": 96, "System uptime": 99.4, "Response time": 1.7, "Stock-out reduction": 38},
            Recommendation.Choice.CONSIDER_SCALEUP,
            "Verified performance is above target on the weighted score. Any wider deployment should still be a government decision, with security review repeated.",
        )
        agro = self._application(self.startups["AgroAI"], "agri", Application.Status.PILOT_COMPLETED, proposal="AgroAI will detect soybean and wheat disease from field images, work on low bandwidth, and route every advisory through the extension officer. False-positive review is built into the officer screen.")
        self._eval(agro, {"technical_feasibility": 8, "innovation": 8, "problem_relevance": 9, "scalability": 7, "technical_capability": 8, "relevant_experience": 7}, "APPROVE_FOR_PILOT", "Relevant to the extension workflow. Officer review must remain mandatory.")
        self._pilot(
            agro, Pilot.Status.COMPLETED, TODAY - timedelta(days=100), TODAY - timedelta(days=20),
            "Sehore block",
            [
                {"name": "Detection accuracy", "target": 85, "unit": "percent", "weight": 45, "priority": "MUST_HAVE", "direction": "HIGHER_IS_BETTER", "weekly": [74, 78, 80, 83, 85, 86, 87, 88]},
                {"name": "False positive rate", "target": 8, "unit": "percent", "weight": 25, "priority": "MUST_HAVE", "direction": "LOWER_IS_BETTER", "weekly": [12, 10, 9.5, 9, 8.4, 8, 7.6, 7.2]},
                {"name": "Farmer coverage", "target": 70, "unit": "percent", "weight": 20, "priority": "BETTER_TO_HAVE", "direction": "HIGHER_IS_BETTER", "weekly": [40, 48, 55, 60, 63, 65, 67, 68]},
                {"name": "Alert latency", "target": 6, "unit": "hours", "weight": 10, "priority": "NICE_TO_HAVE", "direction": "LOWER_IS_BETTER", "weekly": [10, 8, 7, 6.5, 6, 5.5, 5.2, 5]},
            ],
            [("Prototype ready", 250000, 2, "COMPLETE"), ("Integration complete", 250000, 4, "COMPLETE"), ("Pilot complete", 300000, 8, "COMPLETE"), ("Validation complete", 200000, 12, "COMPLETE")],
            8,
            {"Detection accuracy": 88, "False positive rate": 7.2, "Farmer coverage": 68, "Alert latency": 5},
            Recommendation.Choice.CONSIDER_PROCUREMENT,
            "Strong verified result. Coverage is still slightly under target, so a limited procurement geography is the more cautious reading.",
        )
        med = self._application(self.startups["MedPredict"], "tele", Application.Status.PILOT_COMPLETED, proposal="MedPredict provides an ANM triage aid with reasons, offline capture and an audit trail. It does not replace the medical officer.")
        self._eval(med, {"technical_feasibility": 7, "innovation": 7, "problem_relevance": 8, "scalability": 6, "technical_capability": 7, "relevant_experience": 7}, "APPROVE_FOR_PILOT", "Clinically bounded enough for a supervised pilot.")
        self._pilot(
            med, Pilot.Status.COMPLETED, TODAY - timedelta(days=96), TODAY - timedelta(days=18),
            "Raipur rural HWCs",
            [
                {"name": "Triage agreement", "target": 90, "unit": "percent", "weight": 40, "priority": "MUST_HAVE", "direction": "HIGHER_IS_BETTER", "weekly": [78, 80, 82, 83, 84, 85, 85.5, 86]},
                {"name": "Referral time", "target": 3, "unit": "minutes", "weight": 30, "priority": "MUST_HAVE", "direction": "LOWER_IS_BETTER", "weekly": [4.6, 4.2, 4.0, 3.8, 3.6, 3.5, 3.45, 3.4]},
                {"name": "Uptime", "target": 98, "unit": "percent", "weight": 20, "priority": "BETTER_TO_HAVE", "direction": "HIGHER_IS_BETTER", "weekly": [95, 96, 97, 97.5, 98, 98.4, 98.8, 99]},
                {"name": "Referral appropriateness", "target": 80, "unit": "percent", "weight": 10, "priority": "NICE_TO_HAVE", "direction": "HIGHER_IS_BETTER", "weekly": [68, 70, 72, 73, 74, 75, 75.5, 76]},
            ],
            [("Prototype ready", 200000, 2, "COMPLETE"), ("Integration complete", 200000, 5, "COMPLETE"), ("Pilot complete", 250000, 8, "COMPLETE"), ("Validation complete", 150000, 12, "COMPLETE")],
            8,
            {"Triage agreement": 86, "Referral time": 3.4, "Uptime": 99, "Referral appropriateness": 76},
            Recommendation.Choice.ADDITIONAL_PILOT,
            "Referral time is a MUST HAVE KPI below the attention line. Do not let uptime hide it. An additional supervised pilot is the cautious recommendation.",
        )
        ops = self._application(self.startups["SmartOps"], "fleet", Application.Status.PILOT_COMPLETED, proposal="SmartOps scores breakdown risk from telematics and workshop history and proposes workshop slots. False alarms are reviewed weekly.")
        self._eval(ops, {"technical_feasibility": 6, "innovation": 6, "problem_relevance": 7, "scalability": 5, "technical_capability": 6, "relevant_experience": 5}, "APPROVE_FOR_PILOT", "Worth a bounded depot pilot. Claims should be checked against workshop logs.")
        self._pilot(
            ops, Pilot.Status.COMPLETED, TODAY - timedelta(days=90), TODAY - timedelta(days=14),
            "Hyderabad municipal workshop",
            [
                {"name": "Breakdown reduction", "target": 30, "unit": "percent", "weight": 40, "priority": "MUST_HAVE", "direction": "HIGHER_IS_BETTER", "weekly": [8, 10, 12, 14, 16, 18, 21, 24]},
                {"name": "Prediction lead time", "target": 7, "unit": "days", "weight": 30, "priority": "MUST_HAVE", "direction": "HIGHER_IS_BETTER", "weekly": [2, 2.5, 3, 3.4, 3.8, 4.2, 4.6, 5]},
                {"name": "False alarm rate", "target": 10, "unit": "percent", "weight": 20, "priority": "BETTER_TO_HAVE", "direction": "LOWER_IS_BETTER", "weekly": [22, 20, 18, 17, 16, 15, 14.5, 14]},
                {"name": "Workshop adoption", "target": 75, "unit": "percent", "weight": 10, "priority": "NICE_TO_HAVE", "direction": "HIGHER_IS_BETTER", "weekly": [30, 40, 48, 55, 60, 64, 67, 70]},
            ],
            [("Prototype ready", 150000, 2, "COMPLETE"), ("Integration complete", 150000, 5, "DELAYED"), ("Pilot complete", 200000, 8, "COMPLETE"), ("Validation complete", 100000, 12, "PENDING")],
            8,
            {"Breakdown reduction": 24, "Prediction lead time": 5, "False alarm rate": 14, "Workshop adoption": 70},
            Recommendation.Choice.DO_NOT_RECOMMEND,
            "Both MUST HAVE KPIs are materially below target. Do not recommend procurement on this evidence.",
            complaint=("False KPI information", "Week 3 breakdown-reduction claim did not match the workshop register. Later weeks were corrected and the final figure was verified downward.", "CLOSED", "The early sheet used dispatched jobs, not completed jobs. Corrected.", "Explanation accepted after register check. Final score uses the corrected verified value."),
        )
        waste = self._application(self.startups["WasteFlow"], "waste", Application.Status.PILOT_ACTIVE, proposal="WasteFlow retrofits fill sensors and recomputes collection routes each morning, with a ward dashboard for the health inspector.")
        self._eval(waste, {"technical_feasibility": 8, "innovation": 7, "problem_relevance": 8, "scalability": 7, "technical_capability": 7, "relevant_experience": 6}, "APPROVE_FOR_PILOT", "Operationally clear. Sensor uptime should be watched.")
        self._pilot(
            waste, Pilot.Status.ACTIVE, TODAY - timedelta(days=35), TODAY + timedelta(days=35),
            "Bengaluru South zone",
            [
                {"name": "Route adherence", "target": 90, "unit": "percent", "weight": 40, "priority": "MUST_HAVE", "direction": "HIGHER_IS_BETTER", "weekly": [81, 84, 86, 88]},
                {"name": "Missed bin rate", "target": 5, "unit": "percent", "weight": 35, "priority": "MUST_HAVE", "direction": "LOWER_IS_BETTER", "weekly": [7.2, 6.4, 5.8, 5.5]},
                {"name": "Fuel reduction", "target": 12, "unit": "percent", "weight": 25, "priority": "BETTER_TO_HAVE", "direction": "HIGHER_IS_BETTER", "weekly": [4, 6, 7.5, 8]},
            ],
            [("Prototype ready", 200000, 2, "COMPLETE"), ("Integration complete", 200000, 4, "COMPLETE"), ("Pilot deployment", 250000, 6, "PENDING"), ("Validation complete", 150000, 10, "PENDING")],
            5, late_week=5,
        )
        water = self._application(self.startups["AquaSense"], "water", Application.Status.PILOT_ACTIVE, proposal="AquaSense combines night-flow, pressure and acoustic sensing to cluster suspected leaks and raise municipal work orders in Cuttack wards 12 to 18.")
        self._eval(water, {"technical_feasibility": 7, "innovation": 7, "problem_relevance": 9, "scalability": 6, "technical_capability": 7, "relevant_experience": 6}, "APPROVE_FOR_PILOT", "Local team is an advantage for Odisha field work.")
        self._pilot(
            water, Pilot.Status.ACTIVE, TODAY - timedelta(days=28), TODAY + timedelta(days=42),
            "Cuttack wards 12–18",
            [
                {"name": "Confirmed leak rate", "target": 70, "unit": "percent", "weight": 45, "priority": "MUST_HAVE", "direction": "HIGHER_IS_BETTER", "weekly": [48, 55, 61]},
                {"name": "Detection lead time", "target": 24, "unit": "hours", "weight": 30, "priority": "BETTER_TO_HAVE", "direction": "LOWER_IS_BETTER", "weekly": [40, 34, 30]},
                {"name": "Sensor uptime", "target": 95, "unit": "percent", "weight": 25, "priority": "MUST_HAVE", "direction": "HIGHER_IS_BETTER", "weekly": [91, 93, 94]},
            ],
            [("Prototype ready", 180000, 2, "COMPLETE"), ("Integration complete", 180000, 4, "PENDING"), ("Pilot deployment", 200000, 6, "PENDING"), ("Validation complete", 120000, 10, "PENDING")],
            3,
            complaint=("Missed field deployment", "The week-2 night-flow visit for ward 15 was not attended. The startup report still marked the ward as surveyed.", "OPEN", "", ""),
        )
        edu = self._application(self.startups["EduTrack"], "attendance", Application.Status.PILOT_ACTIVE, proposal="EduTrack reads the existing attendance register, scores chronic-absence risk for the block officer, and does not publish a ranking of children.")
        self._eval(edu, {"technical_feasibility": 8, "innovation": 6, "problem_relevance": 8, "scalability": 7, "technical_capability": 7, "relevant_experience": 7}, "APPROVE_FOR_PILOT", "Privacy position is acceptable for a block pilot.")
        self._pilot(
            edu, Pilot.Status.ACTIVE, TODAY - timedelta(days=42), TODAY + timedelta(days=28),
            "Jaipur block schools",
            [
                {"name": "Risk-list precision", "target": 80, "unit": "percent", "weight": 50, "priority": "MUST_HAVE", "direction": "HIGHER_IS_BETTER", "weekly": [68, 72, 75, 77, 79]},
                {"name": "Register coverage", "target": 95, "unit": "percent", "weight": 30, "priority": "MUST_HAVE", "direction": "HIGHER_IS_BETTER", "weekly": [80, 86, 90, 93, 94]},
                {"name": "Officer review time", "target": 15, "unit": "minutes", "weight": 20, "priority": "NICE_TO_HAVE", "direction": "LOWER_IS_BETTER", "weekly": [28, 24, 20, 18, 16]},
            ],
            [("Prototype ready", 120000, 2, "COMPLETE"), ("Integration complete", 150000, 4, "COMPLETE"), ("Pilot deployment", 150000, 6, "COMPLETE"), ("Validation complete", 100000, 10, "PENDING")],
            5,
        )
        path = self._application(self.startups["PathFind"], "traffic", Application.Status.PILOT_ACTIVE, proposal="PathFind forecasts 30-minute corridor congestion and exports a brief the control room can compare with the signal plan.")
        self._eval(path, {"technical_feasibility": 7, "innovation": 7, "problem_relevance": 8, "scalability": 6, "technical_capability": 7, "relevant_experience": 6}, "APPROVE_FOR_PILOT", "Keep the control room in the loop. Do not push signal changes automatically.")
        self._pilot(
            path, Pilot.Status.ACTIVE, TODAY - timedelta(days=21), TODAY + timedelta(days=35),
            "Delhi Ring Road sample",
            [
                {"name": "Forecast accuracy", "target": 85, "unit": "percent", "weight": 50, "priority": "MUST_HAVE", "direction": "HIGHER_IS_BETTER", "weekly": [71, 74]},
                {"name": "Brief latency", "target": 5, "unit": "minutes", "weight": 25, "priority": "BETTER_TO_HAVE", "direction": "LOWER_IS_BETTER", "weekly": [9, 7]},
                {"name": "Corridor coverage", "target": 8, "unit": "corridors", "weight": 25, "priority": "MUST_HAVE", "direction": "HIGHER_IS_BETTER", "weekly": [4, 5]},
            ],
            [("Prototype ready", 160000, 2, "COMPLETE"), ("Integration complete", 160000, 4, "PENDING"), ("Pilot deployment", 180000, 6, "PENDING"), ("Validation complete", 100000, 8, "PENDING")],
            3, clarify_week=3,
        )
        grid = self._application(self.startups["UjjwalGrid"], "street", Application.Status.PILOT_ACTIVE, proposal="UjjwalGrid monitors lighting feeders at night and raises a crew work order when a stretch stays dark.")
        self._eval(grid, {"technical_feasibility": 7, "innovation": 6, "problem_relevance": 8, "scalability": 7, "technical_capability": 6, "relevant_experience": 5}, "APPROVE_FOR_PILOT", "Straightforward municipal operations pilot.")
        self._pilot(
            grid, Pilot.Status.ACTIVE, TODAY - timedelta(days=18), TODAY + timedelta(days=38),
            "Ahmedabad west zone",
            [
                {"name": "Fault detection", "target": 85, "unit": "percent", "weight": 50, "priority": "MUST_HAVE", "direction": "HIGHER_IS_BETTER", "weekly": [70, 76]},
                {"name": "False fault rate", "target": 8, "unit": "percent", "weight": 30, "priority": "MUST_HAVE", "direction": "LOWER_IS_BETTER", "weekly": [14, 11]},
                {"name": "Crew response", "target": 12, "unit": "hours", "weight": 20, "priority": "BETTER_TO_HAVE", "direction": "LOWER_IS_BETTER", "weekly": [20, 16]},
            ],
            [("Prototype ready", 100000, 2, "COMPLETE"), ("Integration complete", 120000, 4, "PENDING"), ("Pilot deployment", 120000, 6, "PENDING"), ("Validation complete", 80000, 8, "PENDING")],
            2,
        )

    def _open_cases(self):
        cold = self._application(
            self.startups["AarogyaNode"], "cold", Application.Status.CLARIFICATION_REQUIRED,
            proposal="AarogyaNode can extend a telehealth workflow to cold-chain excursion risk, but device ownership and after-hours alerting are not yet described.",
        )
        Evaluation.objects.create(
            application=cold,
            evaluator=self.users["evaluator@gov.in"],
            scores={"technical_feasibility": 6, "innovation": 5, "problem_relevance": 7, "scalability": 5, "technical_capability": 6, "relevant_experience": 4},
            comments="Clarify who owns the temperature devices and how an excursion alert reaches the immunisation officer after office hours.",
            decision=Evaluation.Decision.REQUEST_CLARIFICATION,
            decided_at=timezone.now() - timedelta(days=3),
        )
        cold.clarification_request = "Clarify device ownership, after-hours alerting, and whether any medicine-demand model is actually reused."
        cold.save(update_fields=["clarification_request"])
        sheetal = self._application(self.startups["SheetalCold"], "cold", Application.Status.APPROVED_FOR_PILOT, proposal="SheetalCold logs vaccine temperatures from store to session site and raises an excursion alert the immunisation officer can audit.")
        self._eval(sheetal, {"technical_feasibility": 7, "innovation": 6, "problem_relevance": 8, "scalability": 6, "technical_capability": 6, "relevant_experience": 5}, "APPROVE_FOR_PILOT", "Approved for a small store pilot. Contract not yet sent.")
        pending = Pilot.objects.create(
            code=f"PIL-2026-{Pilot.objects.count() + 1:04d}",
            application=sheetal,
            startup=sheetal.startup,
            problem_statement=sheetal.problem_statement,
            procurement_officer=self.users["procurement@gov.in"],
            field_evaluator=self.users["field2@gov.in"],
            location="Cuttack vaccine store",
            start_date=TODAY + timedelta(days=14),
            end_date=TODAY + timedelta(days=70),
            joining_deadline=TODAY + timedelta(days=10),
            duration_weeks=8,
            responsibilities="Install loggers at the district store and two session sites. Submit weekly excursion logs.",
            government_support="Access to the store temperature log and a nodal immunisation officer.",
            payment_conditions="No payment until the joining inspection is verified.",
            security_requirements="No beneficiary data is in scope.",
            status=Pilot.Status.CONTRACT_PENDING,
        )
        Contract.objects.create(
            pilot=pending,
            contract_no=f"PRAVAH/PC/2026/{pending.id:04d}",
            status=Contract.Status.SENT,
            kpi_method=Contract.KPIMethod.EXTRACT,
            sent_at=timezone.now() - timedelta(days=1),
            body_text="Accuracy target 90 percent. Response time target 2 seconds. Uptime target 99 percent. Field adoption target 80 percent.",
        )
        from pilots.services import write_unsigned_contract

        write_unsigned_contract(pending)
        sheetal.status = Application.Status.CONTRACT_PENDING
        sheetal.save(update_fields=["status"])
        KPI.objects.create(pilot=pending, name="Excursion detection", target=90, unit="percent", weight=50, priority="MUST_HAVE", direction="HIGHER_IS_BETTER", max_score=120, source="MANUAL", order=1)
        KPI.objects.create(pilot=pending, name="Logger uptime", target=98, unit="percent", weight=30, priority="MUST_HAVE", direction="HIGHER_IS_BETTER", max_score=120, source="MANUAL", order=2)
        KPI.objects.create(pilot=pending, name="Alert latency", target=15, unit="minutes", weight=20, priority="BETTER_TO_HAVE", direction="LOWER_IS_BETTER", max_score=120, source="MANUAL", order=3)
        pending.contract.kpi_method = Contract.KPIMethod.MANUAL
        pending.contract.kpis_finalized = True
        pending.contract.save()
        rejected = self._application(self.startups["DawaWatch"], "medicine", Application.Status.REJECTED, readiness="YES", proposal="A generic dashboard without a forecasting method.", reason="Technical evaluation did not establish a forecasting method.")
        self._eval(rejected, {"technical_feasibility": 4, "innovation": 3, "problem_relevance": 5, "scalability": 3, "technical_capability": 4, "relevant_experience": 3}, "REJECT", "The proposal does not explain how a stock-out prediction is produced.")
        self._application(self.startups["GramSetu"], "agri", Application.Status.REJECTED_DEADLINE, readiness="NO", reason="REJECTED — CANNOT MEET PILOT DEADLINE")
        sky = self._application(self.startups["BharatSky"], "drone", Application.Status.PILOT_CANCELLED, proposal="BharatSky will highlight imagery change for a human surveyor and will not generate a penalty.")
        self._eval(sky, {"technical_feasibility": 7, "innovation": 7, "problem_relevance": 7, "scalability": 5, "technical_capability": 6, "relevant_experience": 5}, "APPROVE_FOR_PILOT", "Approved, later cancelled for field-access reasons.")
        cancelled = self._pilot(
            sky, Pilot.Status.CANCELLED, TODAY - timedelta(days=40), TODAY + timedelta(days=20),
            "Pimpri-Chinchwad sample wards",
            [
                {"name": "Review precision", "target": 80, "unit": "percent", "weight": 60, "priority": "MUST_HAVE", "direction": "HIGHER_IS_BETTER", "weekly": [60]},
                {"name": "Surveyor time", "target": 20, "unit": "minutes", "weight": 40, "priority": "BETTER_TO_HAVE", "direction": "LOWER_IS_BETTER", "weekly": [35]},
            ],
            [("Prototype ready", 100000, 2, "PENDING"), ("Field sortie", 200000, 4, "PENDING"), ("Review complete", 100000, 6, "PENDING"), ("Validation complete", 50000, 8, "PENDING")],
            1,
        )
        cancelled.cancellation_reason = "Field access to the sample wards was withdrawn. Continuing the pilot would not produce verifiable evidence."
        cancelled.cancelled_at = timezone.now() - timedelta(days=6)
        cancelled.cancelled_by = self.users["procurement@gov.in"]
        cancelled.status = Pilot.Status.CANCELLED
        cancelled.save()
        for company, key, status in [
            ("LekhaAI", "grievance", Application.Status.UNDER_TECHNICAL_EVALUATION),
            ("NirmalCity", "waste", Application.Status.UNDER_TECHNICAL_EVALUATION),
            ("CityPulse", "traffic", Application.Status.SUBMITTED),
            ("JalDhara", "water", Application.Status.ELIGIBILITY_CHECK),
        ]:
            self._application(self.startups[company], key, status, proposal=f"{company} proposes a bounded pilot aligned to the problem statement, with a human reviewer retained.")

    def _filler_applications(self):
        keys = ["medicine", "waste", "agri", "traffic", "water", "attendance", "tele", "fleet", "street", "grievance"]
        fillers = [s for name, s in self.startups.items() if name not in {"NovaTech", "AgroAI", "MedPredict", "SmartOps"}]
        pending_needed = 11 - Application.objects.filter(status=Application.Status.UNDER_TECHNICAL_EVALUATION).count()
        made = 0
        for startup in fillers:
            for key in keys:
                if Application.objects.filter(startup=startup, problem_statement=self.problems[key]).exists():
                    continue
                if made < pending_needed:
                    status = Application.Status.UNDER_TECHNICAL_EVALUATION
                elif made % 3 == 0:
                    status = Application.Status.SUBMITTED
                else:
                    status = Application.Status.ELIGIBILITY_CHECK
                self._application(startup, key, status, proposal="")
                made += 1
                if Application.objects.count() >= 42 and pending_needed <= 0:
                    return
                if Application.objects.count() >= 42 and Application.objects.filter(status=Application.Status.UNDER_TECHNICAL_EVALUATION).count() >= 11:
                    return

    def _notify(self):
        notify("Problem Statement Alert", "No startup has been selected for AI-Based Public Grievance Routing for an extended period. Please review eligibility, requirements, applications and timeline.", category="NO_SELECTION", link=f"/government/problem-statements/{self.problems['grievance'].id}", recipient=self.users["admin@gov.in"])
        notify("Document expiring soon", "Your ISO 27001 certificate will expire soon. Please upload the renewed document.", category="DOCUMENT_EXPIRY", link="/startup/documents", recipient=self.users["nova@novatech.in"])
        notify("Weekly pilot report is overdue", "Weekly pilot report is overdue. Please submit the report or explain the delay.", category="LATE_REPORT", link="/startup/pilots", recipient=self.users["waste@wasteflow.in"])
        notify("Contract pending", "A pilot contract is waiting for SheetalCold to accept and upload the signed copy.", category="CONTRACT", link="/procurement/pilots", recipient=self.users["procurement@gov.in"])
        notify("Field verification pending", "AquaSense week reports and an open complaint need your attention. Your name is not shown to the startup.", category="FIELD_VERIFICATION", link="/field/pilots", recipient=self.users["field@gov.in"])
        notify("New application in queue", "Technical evaluations are waiting in your queue.", category="APPLICATION", link="/evaluator/applications", recipient=self.users["evaluator@gov.in"])
