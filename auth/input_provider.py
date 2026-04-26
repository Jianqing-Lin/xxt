import getpass


class InputProvider:
    def __init__(self, logger):
        self.log = logger

    def read_credentials(self) -> tuple[str, str]:
        try:
            user = input("User: ").strip()
        except EOFError:
            self.log("No interactive stdin available for User input.", 4)
            raise SystemExit(1)
        if not user:
            self.log("User is required.", 4)
            raise SystemExit(1)

        try:
            passwd = getpass.getpass("Passwd: ")
        except EOFError:
            self.log("No interactive stdin available for Passwd input.", 4)
            raise SystemExit(1)
        if not passwd:
            self.log("Passwd is required.", 4)
            raise SystemExit(1)
        return user, passwd
