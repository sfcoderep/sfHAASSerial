-- sfHAASSerial database schema
-- Run once to set up all tables.
-- Compatible with MySQL 8.0+

CREATE DATABASE IF NOT EXISTS sfcncpool
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;

USE sfcncpool;

-- -----------------------------------------------------------------------
-- cnc_data
-- Historian-filtered machine state.  Rows are written only when values
-- change beyond deadband (or every 5 minutes as a force write).
-- Grafana queries use the LAST value per window — this works correctly
-- even with sparse rows because you step-interpolate between writes.
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cnc_data (
    id                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    machine_id        VARCHAR(32)     NOT NULL,
    collected_at      DATETIME(3)     NOT NULL,

    -- Identity (rarely changes — written on force-write)
    serial_number     VARCHAR(32),
    software_ver      VARCHAR(32),
    mode              VARCHAR(32),

    -- Tool
    tool_changes      INT UNSIGNED,
    current_tool      SMALLINT UNSIGNED,

    -- Cumulative timers (HH:MM:SS strings from HAAS)
    power_on_time     VARCHAR(16),
    cycle_start_time  VARCHAR(16),

    -- Program state
    program           VARCHAR(64),
    program_status    VARCHAR(32),
    parts_count       INT UNSIGNED,

    -- Axis positions (inches or mm depending on machine config)
    x_position        DECIMAL(12,4),
    y_position        DECIMAL(12,4),
    z_position        DECIMAL(12,4),
    a_position        DECIMAL(12,4),
    b_position        DECIMAL(12,4),

    -- Spindle / feed
    spindle_speed     INT UNSIGNED,
    feed_rate         DECIMAL(10,2),

    -- Full raw Q-code dump for debugging
    raw_response      JSON,

    PRIMARY KEY (id),
    INDEX idx_machine_time (machine_id, collected_at),
    INDEX idx_time         (collected_at)
) ENGINE=InnoDB ROW_FORMAT=COMPRESSED;


-- -----------------------------------------------------------------------
-- cnc_events
-- Every discrete state transition.  Never historian-filtered.
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cnc_events (
    id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    machine_id    VARCHAR(32)     NOT NULL,
    event_type    VARCHAR(64)     NOT NULL,
    event_time    DATETIME(3)     NOT NULL,
    payload       JSON,

    PRIMARY KEY (id),
    INDEX idx_machine_event (machine_id, event_type, event_time),
    INDEX idx_time          (event_time)
) ENGINE=InnoDB ROW_FORMAT=COMPRESSED;


-- -----------------------------------------------------------------------
-- cnc_alarms
-- Active and historical alarms.  One row per alarm occurrence.
-- cleared_at IS NULL means the alarm is currently active.
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cnc_alarms (
    id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    machine_id     VARCHAR(32)     NOT NULL,
    alarm_code     VARCHAR(16)     NOT NULL,
    alarm_message  VARCHAR(256),
    first_seen     DATETIME(3)     NOT NULL,
    last_seen      DATETIME(3)     NOT NULL,
    cleared_at     DATETIME(3),

    PRIMARY KEY (id),
    -- Unique constraint used by ON DUPLICATE KEY UPDATE for active alarms
    UNIQUE KEY uq_active_alarm (machine_id, alarm_code, cleared_at),
    INDEX idx_machine    (machine_id),
    INDEX idx_active     (cleared_at)
) ENGINE=InnoDB;


-- -----------------------------------------------------------------------
-- cnc_heartbeat
-- One row per machine, updated every poll.  Alerting watchdog reads this.
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cnc_heartbeat (
    machine_id   VARCHAR(32)  NOT NULL,
    last_seen    DATETIME(3)  NOT NULL,

    PRIMARY KEY (machine_id)
) ENGINE=InnoDB;


-- -----------------------------------------------------------------------
-- Convenience view: current machine status (latest row per machine)
-- Grafana "Current Status" panel uses this.
-- -----------------------------------------------------------------------
CREATE OR REPLACE VIEW v_machine_current AS
SELECT
    d.machine_id,
    d.collected_at,
    d.program_status,
    d.program,
    d.current_tool,
    d.parts_count,
    d.spindle_speed,
    d.feed_rate,
    d.x_position,
    d.y_position,
    d.z_position,
    h.last_seen,
    TIMESTAMPDIFF(SECOND, h.last_seen, NOW()) AS seconds_since_heartbeat,
    (SELECT COUNT(*) FROM cnc_alarms a
     WHERE a.machine_id = d.machine_id AND a.cleared_at IS NULL) AS active_alarm_count
FROM cnc_data d
INNER JOIN cnc_heartbeat h USING (machine_id)
WHERE d.id = (
    SELECT MAX(id) FROM cnc_data d2 WHERE d2.machine_id = d.machine_id
);


-- -----------------------------------------------------------------------
-- Convenience view: cycle time statistics per program
-- -----------------------------------------------------------------------
CREATE OR REPLACE VIEW v_cycle_stats AS
SELECT
    machine_id,
    JSON_UNQUOTE(JSON_EXTRACT(payload, '$.program'))    AS program,
    COUNT(*)                                             AS cycles,
    ROUND(AVG(JSON_EXTRACT(payload, '$.cycle_time_sec')), 1) AS avg_cycle_sec,
    ROUND(MIN(JSON_EXTRACT(payload, '$.cycle_time_sec')), 1) AS min_cycle_sec,
    ROUND(MAX(JSON_EXTRACT(payload, '$.cycle_time_sec')), 1) AS max_cycle_sec,
    DATE(event_time)                                     AS run_date
FROM cnc_events
WHERE event_type = 'cycle_stop'
  AND JSON_EXTRACT(payload, '$.cycle_time_sec') IS NOT NULL
GROUP BY machine_id, program, run_date;
