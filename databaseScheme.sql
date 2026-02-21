-- example contestants table, waiting for exact fields to be collected
CREATE TABLE contestants (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    surname TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    phone TEXT NOT NULL,
    school TEXT NOT NULL,
    class_and_profile TEXT NOT NULL,
    city TEXT NOT NULL,
    birthdate DATE NOT NULL,

    supervisor_name TEXT NOT NULL,
    supervisor_surname TEXT NOT NULL,
    supervisor_info TEXT NOT NULL,

    previous_accomplishments TEXT,
    about TEXT NOT NULL,
    interests TEXT NOT NULL,
    contributions TEXT NOT NULL,
    story TEXT NOT NULL,

    topic TEXT NOT NULL,
    whytopic TEXT NOT NULL,
    persuation TEXT NOT NULL,
    experience TEXT NOT NULL,
    ways_of_grabing_interest TEXT NOT NULL,

    video_file_path TEXT,
    rules_accepted BOOLEAN NOT NULL,
    
    created_at TIMESTAMPTZ DEFAULT now()
);

-- viewers table, subject to change
CREATE TABLE viewers (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    surname TEXT NOT NULL,
    school TEXT,
    email TEXT NOT NULL UNIQUE,
    phone TEXT NOT NULL,
    consent_file_path TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- volunteers table, subject to change
CREATE TABLE volunteers (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    surname TEXT NOT NULL,
    school TEXT,
    email TEXT NOT NULL,
    phone TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

--votes table
CREATE TABLE votes (
    id SERIAL PRIMARY KEY,
    chosen_contestant_id INTEGER NOT NULL REFERENCES contestants(id),
    voter_id INTEGER NOT NULL REFERENCES viewers(id),
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT one_vote_per_contestant_per_viewer UNIQUE (voter_id,chosen_contestant_id)
)