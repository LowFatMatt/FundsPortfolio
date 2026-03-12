recommendations = [16.67, 16.67, 16.66, 50.00]
rounded = [round(x, 1) for x in recommendations]
print(f"Original sum: {sum(recommendations)}")
print(f"Rounded sum: {sum(rounded)}")
print(f"Rounded values: {rounded}")
