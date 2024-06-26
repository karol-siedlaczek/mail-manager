#!/usr/bin/env python3

import os
import re
import yaml
from getpass import getpass
import argparse
import logging as log
import mysql.connector
from tabulate import tabulate
from mysql.connector.errors import InterfaceError, DatabaseError

CONFIG_FILE = '/etc/mail-manager/mail-manager.yaml'

DOMAINS_TABLE = 'domains'
USERS_TABLE = 'users'
FORWARDINGS_TABLE = 'forwardings'
AUDIT_LOGS_TABLE = 'audit_logs'

TABLE_CHOICES = [DOMAINS_TABLE, USERS_TABLE, FORWARDINGS_TABLE]

class MailManager:
    def __init__(self, database):
        self.database = database

    def create(self, table_name, domain_name=None, email_address=None):  # selector may be id or full name
        query = None
        if table_name == DOMAINS_TABLE:
            if not domain_name:
                domain_name = input(f'Type a domain name for new record in "{table_name}" table:\n')
            query = f"INSERT INTO {table_name} (name) VALUES ('{domain_name}')"
        elif table_name == USERS_TABLE:
            if not email_address:
                email_address = input(f'Type user email address for new record in "{table_name}" table (<name>@<domain>):\n')
            while not MailManager.is_valid_email(email_address):
                email_address = input(f'Email address is not valid email, type value again (<name>@<domain>):\n')
            user_name = email_address.split('@')[0]
            user_password = MailManager.get_password(email_address)
            user_domain_id = self.database.select(f"SELECT {DOMAINS_TABLE}.id FROM {DOMAINS_TABLE} WHERE {DOMAINS_TABLE}.name = '{email_address.split('@')[-1]}'", True)
            if not user_domain_id:
                user_domain_id = self.create(DOMAINS_TABLE, email_address.split('@')[-1])
                log.info(f'Domain of "{email_address}" alias not exist, domain "{email_address.split("@")[-1]}" added with "{user_domain_id}" index')
            query = f"INSERT INTO {table_name} (name, domain_id, password) VALUES ('{user_name}', '{user_domain_id}', MD5('{user_password}'))"
        elif table_name == FORWARDINGS_TABLE:
            user_input = input(f'Type a user email or id for new record in "{table_name}" table: \n')
            try:
                self.get_row(table_name, int(user_input))
                forwarding_user_id = self.database.select(f"SELECT {USERS_TABLE}.id FROM {USERS_TABLE} WHERE {USERS_TABLE}.id = {user_input}", True)
            except ValueError:  # forwarding user is email address
                forwarding_user_id = self.database.select(f"""
                    SELECT {USERS_TABLE}.id 
                    FROM {USERS_TABLE}
                    JOIN {DOMAINS_TABLE} ON {DOMAINS_TABLE}.id = {USERS_TABLE}.domain_id
                    WHERE {USERS_TABLE}.name = '{user_input.split('@')[0]}' AND {DOMAINS_TABLE}.name = '{user_input.split('@')[1]}'""", True)
                if not forwarding_user_id:  # user does not exist
                    print(f'User with "{user_input}" email address does not exist, type password to create user')
                    forwarding_user_id = self.create(USERS_TABLE, None, user_input)
                    log.info(f'Email address "{user_input}" does not exist, user "{user_input.split("@")[-1]}" added with "{forwarding_user_id}" index')
            forwarding_destination = input(f'Type a destination email address where the emails should be forwarded (<name>@<domain>):\n')
            while not MailManager.is_valid_email(forwarding_destination):
                forwarding_destination = input(f'Email address is not valid email, type value again (<name>@<domain>):\n')
            if self.is_forwarding_exist(forwarding_user_id, forwarding_destination):
                raise IndexError(f'Forwarding from user with "{forwarding_user_id}" id to "{forwarding_destination}" email address already exist, adding aborted')
            else:
                query = f"INSERT INTO {table_name} (user_id, destination) VALUES('{forwarding_user_id}', '{forwarding_destination}')"
        new_row_id = self.database.insert(query)
        print(f'New row with id "{new_row_id}" added to "{table_name}" table')
        return new_row_id

    def delete(self, table_name, index):
        row, row_name = self.get_row(table_name, index)
        confirmation = input(f'Are you sure you want to delete "{row}" {row_name} from {table_name} table? (yes/no): ')
        if confirmation.lower() == 'yes':
            deleted_row = self.database.select(f"SELECT * FROM {table_name} WHERE id = {index}")[0]
            self.database.delete(f"DELETE FROM {table_name} WHERE id = {index}")
            print(f'Row with id "{index}" deleted from "{table_name}" table')
            log.info(f'row with id "{index}" with values {deleted_row} deleted from "{table_name}"')
        else:
            print(f'Action aborted')

    def update(self, table_name, index):
        password_column = False
        row, row_name = self.get_row(table_name, index)
        columns = self.database.get_column_names(table_name)
        column = input(f'Choose column to update "{row}" {row_name} in {table_name} table, available choices ({", ".join(columns)}):\n')
        while column not in columns:
            column = input(f'Column "{column}" does not exist, choose again column to update, available choices ({", ".join(columns)}):\n')
        old_value = self.database.select(f"SELECT {column} FROM {table_name} WHERE id = {index}", True)
        if column == 'password':
            new_value = self.get_password(row)
            password_column = True
        else:
            new_value = input(f'Type new value for {row} {row_name} in {column} column (current: "{old_value}"):\n')
        if new_value == old_value:
            raise IndexError(f'New value ({new_value if not password_column else "****"}) is equal with old value ({old_value if not password_column else "****"}) in "{column}" column for row with "{index}" index in "{table_name}" table, updating aborted')
        new_value = f"'{new_value}'" if not password_column else f"MD5('{new_value}')"
        self.database.update(f"UPDATE {table_name} SET {column} = {new_value} WHERE id = {index}", True if password_column else False)
        print(f'Value of "{column}" column in "{table_name}" table for row with id "{index}" updated from "{old_value if not password_column else "****"}" to "{new_value if not password_column else "****"}"')
        log.info(f'Value of "{column}" column in "{table_name}" table for row with id "{index}" updated from "{old_value if not password_column else "****"}" to "{new_value if not password_column else "****"}"')

    def get_list(self, table_name, inactive, active, max_rows, filter_value):
        query = None
        headers = None
        if table == DOMAINS_TABLE:
            headers = ['ID', 'Domain name', 'State']
            query = f"""
                SELECT {DOMAINS_TABLE}.id, {DOMAINS_TABLE}.name, {DOMAINS_TABLE}.active 
                FROM {table_name}"""
        elif table == USERS_TABLE:
            headers = ['ID', 'E-mail', 'Quota', 'State']
            query = f"""
                SELECT {USERS_TABLE}.id, CONCAT({USERS_TABLE}.name, '@', {DOMAINS_TABLE}.name), CONCAT(CEILING({USERS_TABLE}.quota / 1024.0 / 1024), ' MB'), {USERS_TABLE}.active 
                FROM {table_name} 
                JOIN {DOMAINS_TABLE} ON {DOMAINS_TABLE}.id = {USERS_TABLE}.domain_id"""
        elif table == FORWARDINGS_TABLE:
            headers = ['ID', 'E-mail', 'Destination', 'State']
            query = f"""
                SELECT {FORWARDINGS_TABLE}.id, CONCAT({USERS_TABLE}.name, '@', {DOMAINS_TABLE}.name), {FORWARDINGS_TABLE}.destination, {FORWARDINGS_TABLE}.active 
                FROM {table_name} 
                JOIN {USERS_TABLE} ON {USERS_TABLE}.id = {FORWARDINGS_TABLE}.user_id 
                JOIN {DOMAINS_TABLE} ON {DOMAINS_TABLE}.id = {USERS_TABLE}.domain_id"""
        if filter_value:  # filtering by domain name
            query += f" WHERE {DOMAINS_TABLE}.name LIKE '%{filter_value}%'"
        if inactive:
            query += f' {"WHERE" if "WHERE" not in query else "AND"} {table_name}.active = false'
        elif active:
            query += f' {"WHERE" if "WHERE" not in query else "AND"} {table_name}.active = true'
        result = self.database.select(f'{query} ORDER BY {table_name}.id LIMIT {max_rows}')
        return MailManager.get_result(table.capitalize(), result, headers)

    def get_audit_logs(self, max_rows, filter_value):
        base_query = f"SELECT user, msg, host, remote_host, pid, timestamp FROM {AUDIT_LOGS_TABLE}"
        if filter_value:
            base_query += f" WHERE user LIKE '%{filter_value}%'"
        result = self.database.select(f'{base_query} ORDER BY timestamp DESC LIMIT {max_rows}')
        return MailManager.get_result(AUDIT_LOGS_TABLE.replace('_', ' ').capitalize(), result, ['User', 'Message', 'Host', 'Remote host', 'PID', 'Timestamp'])

    def get_row(self, table_name, index):
        query = None
        row_name = table_name[:-1]
        if table_name == DOMAINS_TABLE:
            query = f"""
                SELECT {DOMAINS_TABLE}.name 
                FROM {table_name} 
                WHERE {table_name}.id = {index}"""
        elif table_name == USERS_TABLE:
            query = f"""
                SELECT CONCAT({USERS_TABLE}.name, '@', {DOMAINS_TABLE}.name) 
                FROM {table_name} 
                JOIN {DOMAINS_TABLE} ON {DOMAINS_TABLE}.id = {USERS_TABLE}.domain_id 
                WHERE {table_name}.id = {index}"""
        elif table_name == FORWARDINGS_TABLE:
            query = f"""
                SELECT CONCAT({USERS_TABLE}.name, '@', {DOMAINS_TABLE}.name, ' -> ', {FORWARDINGS_TABLE}.destination) 
                FROM {table_name} 
                JOIN {USERS_TABLE} ON {USERS_TABLE}.id = {FORWARDINGS_TABLE}.user_id 
                JOIN {DOMAINS_TABLE} ON {DOMAINS_TABLE}.id = {USERS_TABLE}.domain_id 
                WHERE {table_name}.id = {index}"""
        row = self.database.select(query, True)
        if not row:
            raise LookupError(f'{row_name} with id "{index}" in {table_name} table does not exist')
        return row, row_name

    @staticmethod
    def get_result(title, result, headers):
        if len(result) == 0:
            raise LookupError(f'No results for query')
        return f'{title}\n{tabulate(result, headers=headers)}\n'

    @staticmethod
    def get_password(email_address):
        user_password = getpass(prompt=f'Enter the password for "{email_address}" user: ')
        user_password_retyped = getpass(prompt=f'Retype password for "{email_address}" user: ')
        while user_password != user_password_retyped:
            print('Password does not match. Try again')
            user_password = getpass(prompt=f'Enter the password for "{email_address}" user: ')
            user_password_retyped = getpass(prompt=f'Retype password for "{email_address}" user: ')
        return user_password

    @staticmethod
    def is_valid_email(email):
        regex = re.compile(r'([A-Za-z0-9]+[.-_])*[A-Za-z0-9]+@[A-Za-z0-9-]+(\.[A-Z|a-z]{2,})+')
        if re.fullmatch(regex, email):
            return True
        else:
            return False

    def is_forwarding_exist(self, user_id, destination):
        if self.database.select(f"SELECT {FORWARDINGS_TABLE}.id FROM {FORWARDINGS_TABLE} WHERE {FORWARDINGS_TABLE}.destination = '{destination}' AND {FORWARDINGS_TABLE}.user_id = '{user_id}'", True):
            return True
        else:
            return False


class Database:
    def __init__(self, host, user, port, name, password, password_file):
        if not password and password_file and not os.path.isfile(password_file):
            raise OSError(f'Password file "{password_file}" does not exist, use -P/--password to input password as argument or create this file, see details how to create .my.cnf file in MySQL docs')
        config = {'host': host, 'user': user, 'port': port, 'database': name}
        if password:
            config['password'] = password
        elif password_file:
            config['option_files'] = password_file
        self.connection = mysql.connector.connect(**config)
        self.cursor = self.connection.cursor()

    def __run_query(self, query, sensitive_query=False):
        self.cursor.execute(query)
        if sensitive_query:
            log.debug('Query not logged, because command contains sensitive content')
        else:
            log.debug(f'Execute {query}')

    def insert(self, query):
        self.__run_query(query)
        self.connection.commit()
        return self.cursor.lastrowid  # return newly created row id

    def update(self, query, sensitive_query=False):
        self.__run_query(query, sensitive_query)
        self.connection.commit()

    def delete(self, query):
        self.__run_query(query)
        self.connection.commit()

    def select(self, query, single_value=False):
        self.__run_query(query)
        if single_value:
            try:
                return self.cursor.fetchone()[0]
            except TypeError:  # empty value
                return None
        else:
            return self.cursor.fetchall()

    def get_column_names(self, table_name):
        columns = self.select(f'SHOW columns FROM {table_name}')
        return [column[0] for column in columns]


def parse_args(conf):
    db_conf = conf.get('db')
    parser = argparse.ArgumentParser(description='Script to manage domains, users and forwardings of postfix mail server based on SASL smtp auth')
    parser.add_argument('-H', '--dbHost',
                        help=f'Database host, default is {db_conf.get("host")}',
                        type=str,
                        metavar='host',
                        default=db_conf.get("host"))
    parser.add_argument('-U', '--dbUser',
                        help=f'Database user, default is {db_conf.get("user")}',
                        type=str,
                        metavar='user',
                        default=db_conf.get("user"))
    parser.add_argument('-p', '--dbPort',
                        help=f'Database port, default is {db_conf.get("port")}',
                        type=int,
                        metavar='port',
                        default=db_conf.get("port"))
    parser.add_argument('-D', '--dbName',
                        help=f'Database name, default is {db_conf.get("name")}',
                        type=str,
                        metavar='database',
                        default=db_conf.get("name"))
    parser.add_argument('-P', '--dbPasswd',
                        help='Database password, choose this option if you do not want get password from file',
                        type=str,
                        metavar='password')
    parser.add_argument('--dbPasswdFile',
                        help=f'File with password to database, default is {db_conf.get("pass_file")}',
                        type=str,
                        metavar='file',
                        default=db_conf.get("pass_file"))
    parser.add_argument('-l', '--list',
                        help=f'List users, forwarding or domains table content',
                        type=str,
                        nargs='+',
                        choices=TABLE_CHOICES)
    parser.add_argument('-f', '--filter',
                        help=f'Usable with -l/--list argument to filter output by domain or --logs argument to filter output by user',
                        type=str)
    parser.add_argument('--logs',
                        help='Lists SASL authentication logs from database',
                        action='store_true')
    parser.add_argument('-m', '--maxRows',
                        help=f'Specifies number of log lines which will be printed, default is {conf.get("max_rows")}',
                        type=int,
                        default=conf.get("max_rows"))
    parser.add_argument('--inactive',
                        help=f'Usable with -l/--list argument in order to get only inactive users in output',
                        action='store_true',
                        default=False)
    parser.add_argument('--active',
                        help=f'Usable with -l/--list argument in order to get only active users in output',
                        action='store_true',
                        default=False)
    parser.add_argument('-a', '--add',
                        help='Select table in which a row is to be added',
                        type=str,
                        choices=TABLE_CHOICES)
    parser.add_argument('-u', '--update',
                        help='elect table in which a row is to be updated',
                        type=str,
                        choices=TABLE_CHOICES)
    parser.add_argument('-d', '--delete',
                        help='Select table in which a row is to be deleted',
                        type=str,
                        choices=TABLE_CHOICES)
    parser.add_argument('-i', '--index',
                        help=f'Usable with -u/--update or -d/--delete argument to specify index of database',
                        type=int)
    args = parser.parse_args()
    if (args.update or args.delete) and not args.index:  # when writing data, but no value provided
        raise parser.error('argument -i/--index is required while using -u/--update or -d/--delete argument')
    elif (args.add and args.update and args.delete) or (args.add and args.update) or (args.add and args.delete) or (args.update and args.delete):  # when writing with too many arguments
        raise parser.error('only one argument can be used at once from the -a/--add, -u/--update or -d/--delete arguments')
    elif not args.list and not args.logs and args.filter:  # when filtering, but listing column not selected
        raise parser.error('invalid usage of -f/--filter argument, the -l/--list or --logs argument is required to filter')
    elif not args.list and not args.logs and int(args.maxRows) != int(conf.get('max_rows')):
        raise parser.error('invalid usage of -m/--maxRows argument, the -l/--list or --logs argument is required to specify number of rows in output')
    return args


if __name__ == "__main__":
    with open(CONFIG_FILE, "r") as f:
        conf = yaml.safe_load(f)
    log.basicConfig(filename=conf.get('log_file'), format='%(asctime)s %(name)s %(levelname)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S', level=log.DEBUG)
    args = parse_args(conf)
    try:
        mailManager = MailManager(Database(args.dbHost, args.dbUser, args.dbPort, args.dbName, args.dbPasswd, args.dbPasswdFile))
        if args.add:
            mailManager.create(args.add)
        elif args.update:
            mailManager.update(args.update, args.index)
        elif args.delete:
            mailManager.delete(args.delete, args.index)
        try:
            for table in args.list:
                print(mailManager.get_list(table, args.inactive, args.active, args.maxRows, args.filter))
        except TypeError:  # if no values in args.list
            pass
        if args.logs:
            print(mailManager.get_audit_logs(args.maxRows, args.filter))
    except (OSError, IndexError, InterfaceError, DatabaseError) as e:  # passwd file not exist; cannot connect to mysql; cannot connect to mysql connect(by host)
        log.error(e)
        print(f'ERROR: {e}')
    except LookupError as e:  # no results from query
        print(f'ERROR: {e}')
