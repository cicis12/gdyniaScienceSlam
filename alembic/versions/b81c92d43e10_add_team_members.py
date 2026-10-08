"""Store editable team profiles, preserving the original roster."""
from alembic import op
import sqlalchemy as sa

revision = "b81c92d43e10"
down_revision = "5f4a69ae45f6"
branch_labels = None
depends_on = None

INITIAL_MEMBERS = [{'name': 'Ignacy Salitra',
  'position': 'Leader',
  'description': 'Hej, jestem Ignacy, znajomi mówią do mnie Igi. Jestem w 3 klasie na profilu '
                 'biologiczno-chemicznym i w tym roku mam przyjemność koordynować pracę całego '
                 'zespołu jako lider Gdynia Science Slam 2026. Odpowiadam za wyznaczanie kierunku '
                 'działań oraz podział zadań w teamie. Poza GSS interesuję się polityką, dlatego '
                 'od ponad roku jeżdżę po całej Polsce, biorąc udział w konferencjach Model United '
                 'Nations. Jestem przekonany, że Gdynia Science Slam 2026 będzie najlepszą edycją '
                 'w historii, dlatego już teraz zapraszam Was do aplikowania na prelegenta. Jeśli '
                 'natomiast w tym roku nie czujecie, że to Wasz moment na wystąpienia publiczne, '
                 'zachęcam do aplikowania na widownię lub jako wolontariusz.',
  'photo': '/static/assets/images/team/43.webp'},
 {'name': 'Kinga Nowak',
  'position': 'Deputy Leader',
  'description': 'Hejka! Jestem Kinga i chodzę do klasy 3IB. Możecie mnie kojarzyć z konkursów '
                 'naukowych lub MUNów. Najbardziej lubię się rozwijać i właśnie dlatego jestem '
                 'wniebowzięta, że jestem częścią teamu organizacyjnego Slama i mogę tworzyć '
                 'miejsce skierowane na popularyzacje nauki. Uwielbiam psychologię, neurobiologię, '
                 'geopolitykę, podróżowanie, taniec, a przede wszystkim poznawanie nowych osób. '
                 'Moim niszowym hobby jest spanie i jestem w stanie zasnąć zawsze i wszędzie.',
  'photo': '/static/assets/images/team/41.webp'},
 {'name': 'Natalia Sikorska',
  'position': 'Deputy Leader',
  'description': ' Hej, nazywam się Natalia i chodzę do 3IB w Gdyńskiej Trójce. Moim hobby jest '
                 'gra na pianinie i jazda konna, a także przedmioty ścisłe.',
  'photo': '/static/assets/images/team/42.webp'},
 {'name': 'Natasza Sudoł',
  'position': 'Media',
  'description': 'Hejka kochani! Ja jestem Natasza i na slamie odpowiadam za koordynacje teamu '
                 'social media. Interesuję się nauką, szczególnie fizyką i astronomią, a także '
                 'geopolityką. Nie mogę się doczekać tegorocznego Gdynia Science Slam i mam '
                 'nadzieję że spotkamy się w Gdyni! Widzimy się!',
  'photo': '/static/assets/images/team/28.webp'},
 {'name': 'Antonina Podgórska',
  'position': 'Media',
  'description': 'Hejka, jestem Tosia i w tym roku zajmuje się prowadzeniem mediów Gdynia Science '
                 'Slam, w wolnym czasie lubię grać w tenisa, słuchać muzyki, wychodzić ze '
                 'znajomymi i spać tyle ile mogę. Interesuje mnie anatomia człowieka, a '
                 'szczególnie mózgu. Mam nadzieję, że widzimy się w Gdyni na Science Slamie oraz '
                 'że razem posłuchamy ciekawych wystąpień naszych prelegentów, Do zobaczenia😘!!',
  'photo': '/static/assets/images/team/29.webp'},
 {'name': 'Kuba Kamiński',
  'position': 'Design',
  'description': 'Cześć, jestem Kuba i już trzeci rok z rzędu jestem grafikiem tej konferencji. '
                 'Chodzę do klasy 3IB, a moje zainteresowania to teatr, kino, matematyka hl i '
                 'organizacja Gdynia Science Slam.',
  'photo': '/static/assets/images/team/27.webp'},
 {'name': 'Hania Sajdak',
  'position': 'Head of Partnerships',
  'description': 'Hejka tu Hania z 3 IB, uwielbiam uprawiać sporty - szczególnie taniec, w wolnym '
                 'czasie czytam kryminały , oglądam seriale network drama albo uczę się nowych '
                 'języków.',
  'photo': '/static/assets/images/team/30.webp'},
 {'name': 'Kacper Górski',
  'position': 'Partnerships',
  'description': 'Cześć, jestem pasjonatem nauk ścisłych w szczególności astronomii, chociaż '
                 'uwielbiam też debatować. Interesuję się również filozofią oraz kinem. Do '
                 'zobaczenia podczas GSS!',
  'photo': '/static/assets/images/team/31.webp'},
 {'name': 'Maciej Miłosz',
  'position': 'Partnerships',
  'description': 'Hejka, nazywam się Maciek, uczę się w klasie MYP. Interesuję się w zasadzie '
                 'wszystkim, z czego w największym stopniu literaturą i filozofią. Publikowałem w '
                 'kilku czasopismach literackich i na Substacku. Dzięki skrzyżowaniu pewnych '
                 'stypendiów uczestniczę też w badaniach z zakresu kognitywistyki.',
  'photo': '/static/assets/images/team/32.webp'},
 {'name': 'Marcel Muzyczuk',
  'position': 'IT Specialist',
  'description': 'Siema, jestem Marcel. Na slamie jestem odpowiedzialny za informatykę - od strony '
                 'internetowej, przez zarządzanie zgłoszeniami aż do ogarniania prezentacji. Na '
                 'codzień interesuje się informatyką, matematyką i logistyką ale też historią i '
                 'polityką, więc zainteresowanie mnie prezentacją nie będzie trudne. Mam nadzieję '
                 'że widzimy się w PPNT!',
  'photo': '/static/assets/images/team/33.webp'},
 {'name': 'Oliwia Gatz',
  'position': 'IT Specialist',
  'description': 'Cześć jestem Oliwia. Chodzę do klasy matematyczno-informatycznej, w naszym '
                 'projekcie zajmowałam się razem z Marcelem tworzeniem strony internetowej. W '
                 'wolnym czasie lubię szydełkować, a moje ulubione zwierzątko to szop🦝',
  'photo': '/static/assets/images/team/34.webp'},
 {'name': 'Julia Willma',
  'position': 'Head of Formalities',
  'description': 'Hej, nazywam się Julia i w tej edycji mam okazję odpowiadać za formalności. '
                 'Oprócz head of formalities na GSS jestem też radną w MRM w Gdańsku i miałam już '
                 'okazję uczestniczyć w organizacji paru wydarzeń. Nie mogę się jednak doczekać '
                 'maja kiedy w końcu praca całego teamu będzie widoczna na żywo. You have to be '
                 'there!!',
  'photo': '/static/assets/images/team/35.webp'},
 {'name': 'Lena Borowska',
  'position': 'Formalities',
  'description': 'Hej! Nazywam się Lena i tak jak reszta zespołu interesuje się nauką (oraz '
                 'kryminalistyką), mam nadzieję, że wasza przygoda z Gdynia Science Slam będzie '
                 'niesamowitym przeżyciem pełnym dobrej zabawy, oraz możliwością poznania nowych '
                 'fajnych osób ;))!',
  'photo': '/static/assets/images/team/36.webp'},
 {'name': 'Konstanty Konopka',
  'position': 'Finances',
  'description': 'Hej hej! Jestem Kostek Konopka odpowiadam za finansową stronę projektu. '
                 'Zazwyczaj pracuje z Excelem, zajmuje się wystawianiem faktur oraz przygotowuje '
                 'preliminarze i kosztorysy wydarzenia, dbając o pokrycie projektu oraz brak dziur '
                 'finansowych. Poza projektem uczę się w programie IB, a kiedy nic nie muszę to '
                 'jadę podróż, najlepiej pod namiot jak daleko można.',
  'photo': '/static/assets/images/team/37.webp'},
 {'name': 'Stefan Sadkowski',
  'position': 'Content Creator',
  'description': 'siema, jestem Stefan i w tym roku na Science Slamie będę odpowiadać za content '
                 'na tiktoku naszej konferencji. Chodzę do klasy 1c i możecie mnie kojarzyć ze '
                 'szkolnego tiktoka, nagrałem tam już trochę fajnych filmików, a jakość tych na '
                 'Science Slamie będzie jeszcze lepsza. Wraz z Michałem już nagrywamy filmy, więc '
                 'wyczekujcie ich bo warto!!!!',
  'photo': '/static/assets/images/team/39.webp'},
 {'name': 'Michał Bochentyn',
  'position': 'Content Creator',
  'description': 'Cześć! Nazywam się Michał i jestem uczniem klasy matematyczno-geograficznej. '
                 'Część z Was może mnie kojarzyć ze szkolnego TikToka lub z działalności w '
                 'samorządzie uczniowskim. W tym roku podczas GSS będę pełnił rolę content '
                 'creatora, dlatego możecie spodziewać się wielu materiałów i relacji na naszym '
                 'TikToku. W wolnym czasie interesuję się matematyką, sportem oraz social mediami. '
                 'Zachęcam do śledzenia TikToka i do zobaczenia wkrótce!',
  'photo': '/static/assets/images/team/40.webp'},
 {'name': 'Izabela Radziuk-Śliwińska',
  'position': 'Event Supervisor',
  'description': 'Dzień dobry, nazywam się Izabella Radziuk-Śliwińska, jestem nauczycielką chemii '
                 'i wychowawczynią w III LO w Gdyni. Na studiach swoją pracę magisterską '
                 'realizowałam w Katedrze Chemii Organicznej (w Pracowni Chemii Cukrów), jednak '
                 'najbardziej pasjonuje mnie popularyzacja nauki. Czuję się obdarowana, bo młodzi '
                 'ludzie, których spotykam w szkole są wspaniali i motywują mnie do rozwoju.',
  'photo': '/static/assets/images/team/44.webp'}]


def upgrade():
    table = op.create_table(
        "team_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("position", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("photo", sa.String(500), nullable=False),
    )
    op.bulk_insert(table, INITIAL_MEMBERS)


def downgrade():
    op.drop_table("team_members")
