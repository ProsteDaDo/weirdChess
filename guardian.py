import pieceBase
import moveObj

class Guardian(pieceBase.Piece):
    def __init__(self, x, y, col):
        super().__init__(x, y, col)

    def get_possible_moves(self, game):
        moves = []

        for dx, dy in [(x, y) for x in (-1, 0, 1) for y in (-1, 0, 1) if not (x == y == 0)]:
            killed = () if not game.is_enemy(self.x + dx, self.y + dy, self.color) else (game.board[self.y + dy][self.x + dx],)

            if len(killed) > 0 and type(killed[0]).__name__ == "Mine":
                killed = (killed[0], self)

            if killed != () or game.is_free(self.x + dx, self.y + dy):
                moves.append(moveObj.Move(self, self.x, self.y, self.x + dx, self.y + dy, removed=killed))

        return moves