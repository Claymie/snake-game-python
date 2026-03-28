import pygame
import time
import random

pygame.init()

# Настройки экрана
width, height = 800, 600
dis = pygame.display.set_mode((width, height))
pygame.display.set_caption('Mopsik Snake Game — Pro Edition')

# Цвета
black = (10, 10, 10)
red_body = (255, 0, 0)  # Цвет тела
red_head = (150, 0, 0)  # Цвет ГОЛОВЫ (темно-красный)
green = (0, 255, 100)  # Еда
white = (255, 255, 255)  # Текст

snake_block = 20
snake_speed = 8

clock = pygame.time.Clock()
# Шрифты
font_style = pygame.font.SysFont("arial", 25)
score_font = pygame.font.SysFont("arial", 35)


def Your_score(score):
    value = score_font.render("Счёт: " + str(score), True, white)
    dis.blit(value, [10, 10])


def message(msg, color):
    mesg = font_style.render(msg, True, color)
    dis.blit(mesg, [width / 4, height / 3])


def gameLoop():
    game_over = False
    game_close = False

    x1, y1 = width / 2, height / 2
    x1_change, y1_change = 0, 0

    snake_List = []
    Length_of_snake = 1

    foodx = round(random.randrange(0, width - snake_block) / 20.0) * 20.0
    foody = round(random.randrange(0, height - snake_block) / 20.0) * 20.0

    while not game_over:
        while game_close == True:
            dis.fill(black)
            message("Проигрыш! C - Заново, Q - Выход", white)
            Your_score(Length_of_snake - 1)
            pygame.display.update()
            for event in pygame.event.get():
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_q:
                        game_over = True
                        game_close = False
                    if event.key == pygame.K_c:
                        gameLoop()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                game_over = True
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_LEFT and x1_change == 0:
                    x1_change = -snake_block
                    y1_change = 0
                elif event.key == pygame.K_RIGHT and x1_change == 0:
                    x1_change = snake_block
                    y1_change = 0
                elif event.key == pygame.K_UP and y1_change == 0:
                    y1_change = -snake_block
                    x1_change = 0
                elif event.key == pygame.K_DOWN and y1_change == 0:
                    y1_change = snake_block
                    x1_change = 0

        if x1 >= width or x1 < 0 or y1 >= height or y1 < 0:
            game_close = True
        x1 += x1_change
        y1 += y1_change
        dis.fill(black)

        pygame.draw.rect(dis, green, [foodx, foody, snake_block, snake_block])

        snake_Head = [x1, y1]
        snake_List.append(snake_Head)
        if len(snake_List) > Length_of_snake:
            del snake_List[0]

        for x in snake_List[:-1]:
            if x == snake_Head:
                game_close = True

        # РИСУЕМ ЗМЕЙКУ
        for i, segment in enumerate(snake_List):
            # Если это последний элемент в списке (голова), красим в темно-красный
            if i == len(snake_List) - 1:
                pygame.draw.rect(dis, red_head, [segment[0], segment[1], snake_block, snake_block])
            else:
                pygame.draw.rect(dis, red_body, [segment[0], segment[1], snake_block, snake_block])

        Your_score(Length_of_snake - 1)
        pygame.display.update()

        if x1 == foodx and y1 == foody:
            foodx = round(random.randrange(0, width - snake_block) / 20.0) * 20.0
            foody = round(random.randrange(0, height - snake_block) / 20.0) * 20.0
            Length_of_snake += 1

        clock.tick(snake_speed)

    pygame.quit()
    quit()


gameLoop()