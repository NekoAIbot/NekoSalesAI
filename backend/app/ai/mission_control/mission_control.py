from app.repositories.mission_event_repository import (
    MissionEventRepository,
)


class MissionControl:

    def __init__(self, db):

        self.repo = MissionEventRepository(db)

    def report(
        self,
        source,
        level,
        title,
        message,
    ):

        self.repo.create(
            source=source,
            level=level,
            title=title,
            message=message,
        )

        print()
        print("========== MISSION CONTROL ==========")
        print(level)
        print(source)
        print(title)
        print(message)
        print("====================================")

