CREATE `<DB_NAME>`;
USE `<DB_NAME>`;

CREATE USER `<USER_RO>`@`localhost` IDENTIFIED BY '<PASS>';
CREATE USER `<USER>`@`localhost` IDENTIFIED BY '<PASS>';

CREATE TABLE `domains` (
        `id`			bigint NOT NULL AUTO_INCREMENT,
        `name`			VARCHAR(55) NOT NULL UNIQUE,
        `active`		tinyint(1) DEFAULT '1',
		PRIMARY KEY		(`id`)
);

CREATE TABLE `users` (
        `id`			bigint NOT NULL AUTO_INCREMENT,
        `name`			VARCHAR(255) NOT NULL,
        `domain_id`		bigint,
        `password`		VARCHAR(255) NOT NULL,
        `active`		tinyint(1) DEFAULT '1',
		`quota`			INT(10) DEFAULT '10485760',
		`email`         VARCHAR(105) UNIQUE NOT NULL
		PRIMARY KEY		(`id`),
		CONSTRAINT 		`fk_users_domains` FOREIGN KEY (`domain_id`) REFERENCES `domains`(`id`) ON DELETE NO ACTION
);

CREATE TABLE `forwardings` (
        `id`			bigint NOT NULL AUTO_INCREMENT,
        `user_id`		bigint,
        `destination`	VARCHAR(255) NOT NULL,
        `active`		tinyint(1) DEFAULT '1',
		PRIMARY KEY		(`id`),
		CONSTRAINT 		`fk_forwardings_users`	FOREIGN KEY	(`user_id`) REFERENCES `users`(`id`) ON DELETE NO ACTION
);

CREATE TABLE `audit_logs` (
        `id`            bigint NOT NULL AUTO_INCREMENT,
        `msg`           TEXT,
        `user`          VARCHAR(105) NOT NULL,
        `host`          VARCHAR(105) NOT NULL,
        `remote_host`   VARCHAR(105),
        `pid`           INT,
        `timestamp`     TIMESTAMP NOT NULL,
        PRIMARY KEY     (`id`)
);

CREATE INDEX users_domains_id ON users(`domain_id`);
CREATE INDEX forwardings_users ON forwardings(`user_id`);

GRANT USAGE ON *.* TO `<USER_RO>`@`localhost`;
GRANT USAGE ON *.* TO `<USER>`@`localhost`;


GRANT SELECT ON `<DB_NAME>`.* TO `<USER_RO>`@`localhost`;
GRANT INSERT ON `<DB_NAME>`.`audit_logs` TO `<USER_RO>`@`localhost`;
GRANT SELECT, UPDATE, INSERT, DELETE ON `<DB_NAME>`.* TO `<USER>`@`localhost`;

delimiter $$

DROP TRIGGER IF EXISTS set_email_by_domains_after_update;
CREATE TRIGGER set_email_by_domains_after_update
AFTER UPDATE ON domains
FOR EACH ROW
BEGIN
    IF (NEW.name != OLD.name) THEN
        UPDATE users
        SET users.email = CONCAT(users.name, '@', (SELECT domains.name FROM domains WHERE domains.id = NEW.id))
        WHERE users.domain_id = NEW.id;
    END IF;
END$$

DROP TRIGGER IF EXISTS set_email_by_users_before_update;
CREATE TRIGGER set_email_by_users_before_update
BEFORE UPDATE ON users
FOR EACH ROW
BEGIN
    SET @domain_name := (SELECT domains.name FROM domains WHERE domains.id = NEW.domain_id);
    IF (NEW.name != OLD.name) THEN
        SET NEW.email = CONCAT(NEW.name, '@', @domain_name);
    ELSEIF (NEW.email != CONCAT(NEW.name, '@', @domain_name)) THEN
        SIGNAL SQLSTATE '50001' SET MESSAGE_TEXT = 'Email must contains a consistent username and domain name';
    END IF;
END$$

DROP TRIGGER IF EXISTS set_email_by_users_after_insert;
CREATE TRIGGER set_email_by_users_after_insert
BEFORE INSERT ON users
FOR EACH ROW
BEGIN
    SET NEW.email = CONCAT(NEW.name, '@', (SELECT domains.name FROM domains WHERE domains.id = NEW.domain_id));
END$$
