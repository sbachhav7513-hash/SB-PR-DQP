from market_bot.main import main
from market_bot.secrets import load_local_environment


load_local_environment()


if __name__ == "__main__":
    main()
