from env import load_environment

from tools.fetch_prices import run_fetch_prices

def main():
    load_environment()
    
    # update current prices
    run_fetch_prices()

if __name__ == "__main__":
    main()