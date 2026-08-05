class ThoughtLogger:

    def send(self, thoughts):

        print()
        print("========== AI THOUGHTS ==========")

        for thought in thoughts:

            print(
                f"[{thought['stage']}]",
                thought["message"],
            )

        print("=================================")

