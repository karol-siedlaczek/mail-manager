# Postfix database mail manager

Add/list/delete users, domains, forwardings or virtual accounts in Postfix

## Configuration samples

`main.cf`
```bash
# [...]
virtual_alias_domains = mysql:/etc/postfix/mysql/virtual_domains.cf
virtual_alias_maps = mysql:/etc/postfix/mysql/virtual_forwardings.cf
virtual_mailbox_maps = mysql:/etc/postfix/mysql/virtual_mailboxes.cf
virtual_mailbox_limit = mysql:/etc/postfix/mysql/virtual_mailbox_limit.cf
# [...]
```

---

`smtpd.conf`
```bash
pwcheck_method:         saslauthd
auxprop_plugin:         mysql
mech_list:              PLAIN LOGIN CRAM-MD5 DIGEST-MD5 NTLM
allow_plaintext:        true
sql_engine:             mysql
sql_user:               <DB_USER>
sql_passwd:             <DB_PASSWORD>
sql_hostnames:          <DB_HOST>:<DB_PORT>
sql_database:           <DB_NAME>
#sql_select:            SELECT password FROM users JOIN domains ON users.domain_id = domains.id WHERE users.name='%u' AND domains.domain = '%r'
#sql_select:            SELECT u.password FROM users u JOIN domains d ON d.id = u.domain_id WHERE u.name = '%u' AND d.name = '%r' AND active = true
sql_select:             SELECT password FROM users WHERE email = '%s'
#sql_insert:            INSERT INTO users (name, domain_id, '%p') VALUES ('%u', '%r', '%v')
#sql_update:            UPDATE users SET '%p' = '%v' WHERE users.name = '%u'
log_level:              7
```

---

`virtual_domains.cf`
```bash
user            = <DB_USER>
password        = <DB_PASSWORD>
dbname          = <DB_NAME>
hosts           = <DB_HOST>
query           = SELECT d.name FROM domains d WHERE d.name='%s' AND d.active=true
```

---

`virtual_forwardings.cf`
```bash
user            = <DB_USER>
password        = <DB_PASSWORD>
dbname          = <DB_NAME>
hosts           = <DB_HOST>
query           = SELECT f.destination FROM forwardings f JOIN users u ON u.id = f.user_id WHERE u.email = '%s' AND f.active = true
```

---

`virtual_mailboxes.cf`
```bash
user            = <DB_USER>
password        = <DB_PASSWORD>
dbname          = <DB_NAME>
hosts           = <DB_HOST>
query           = SELECT CONCAT(SUBSTRING_INDEX(d.name,'@',-1),'/', SUBSTRING_INDEX(u.name,'@',1),'/') FROM users u JOIN domains d ON d.id = u.domain_id WHERE u.name = '%u' AND d.name = '%d'
```

---

`virtual_mailbox_limit.cf`
```bash
user            = <DB_USER>
password        = <DB_PASSWORD>
dbname          = <DB_NAME>
hosts           = <DB_HOST>
query           = SELECT u.quota FROM users u JOIN domains d ON d.id = u.domain_id WHERE u.name='%u' AND d.name='%r' AND u.active=true;
```
