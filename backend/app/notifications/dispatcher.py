class NotificationDispatcher:

    def __init__(
        self,
        telegram=None,
        whatsapp=None,
        email=None,
        push=None,
    ):

        self.telegram = telegram
        self.whatsapp = whatsapp
        self.email = email
        self.push = push

    def notify(
        self,
        channel,
        message,
    ):

        if channel == "telegram" and self.telegram:
            return self.telegram.send(message)

        if channel == "whatsapp" and self.whatsapp:
            return self.whatsapp.send(message)

        if channel == "email" and self.email:
            return self.email.send(message)

        if channel == "push" and self.push:
            return self.push.send(message)

        print()
        print("Notification")
        print(channel)
        print(message)

