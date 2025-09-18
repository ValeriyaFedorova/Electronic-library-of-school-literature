-- MySQL dump 10.13  Distrib 8.0.43, for Win64 (x86_64)
--
-- Host: 127.0.0.1    Database: library
-- ------------------------------------------------------
-- Server version	9.4.0

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `books`
--

DROP TABLE IF EXISTS `books`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `books` (
  `id` int NOT NULL AUTO_INCREMENT,
  `title` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `author` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `filename` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `cover_path` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `added_date` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `filename` (`filename`),
  KEY `ix_books_author` (`author`),
  KEY `ix_books_title` (`title`)
) ENGINE=InnoDB AUTO_INCREMENT=17 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `books`
--

LOCK TABLES `books` WRITE;
/*!40000 ALTER TABLE `books` DISABLE KEYS */;
INSERT INTO `books` VALUES (1,'Гранатовый браслет','Куприн А.И.','А. И. Куприн. «Гранатовый браслет».epub','covers/cover_45f84c09.jpg','2025-09-18 14:26:57'),(2,'Гроза','Островский А.Н.','А. Н. Островский. «Гроза».epub','covers/cover_1266e879.jpg','2025-09-18 14:26:57'),(3,'Вишневый сад','Чехов А.П.','А. П. Чехов. «Вишнёвый сад».epub','covers/cover_4b56c2e6.jpg','2025-09-18 14:26:58'),(4,'Горе от ума','Грибоедов А.С.','А. С. Грибоедов. «Горе от ума».epub','covers/cover_eef21cca.jpg','2025-09-18 14:26:58'),(5,'Евгений Онегин','Пушкин А.С.','А. С. Пушкин. «Евгений Онегин».epub','covers/cover_83eef3b1.jpg','2025-09-18 14:26:59'),(6,'Антоновские яблоки','Иван Алексеевич Бунин','И. А. Бунин. «Антоновские яблоки».epub','covers/cover_6f5aec40.jpg','2025-09-18 14:26:59'),(7,'Обломов','Гончаров И.А.','И. А. Гончаров. «Обломов».epub','covers/cover_608e0fe2.jpg','2025-09-18 14:27:00'),(8,'Отцы и дети','Тургенев И.С.','И. С. Тургенев. «Отцы и дети».epub','covers/cover_76da54e7.jpg','2025-09-18 14:27:01'),(9,'Война и мир','Толстой Л.Н.','Л. Н. Толстой. «Война и мир».epub','covers/cover_ad3166cf.jpg','2025-09-18 14:27:02'),(10,'Мастер и Маргарита','Михаил Афанасьевич Булгаков','М. А. Булгаков. «Мастер и Маргарита».epub','covers/cover_f7156d7e.jpg','2025-09-18 14:27:06'),(11,'На дне','Горький М.','М. Горький. «На дне».epub','covers/cover_619efd5c.jpg','2025-09-18 14:27:08'),(12,'Старуха Изергиль','Максим Горький','М. Горький. «Старуха Изергиль».epub','covers/cover_d1341e94.jpg','2025-09-18 14:27:08'),(13,'Герой нашего времени','Лермонтов М.Ю.','М. Ю. Лермонтов. «Герой нашего времени».epub','covers/cover_d4be5624.jpg','2025-09-18 14:27:08'),(14,'Мёртвые души','Гоголь Н.В.','Н. В. Гоголь. «Мертвые души».epub','covers/cover_7a8de0b3.jpg','2025-09-18 14:27:08'),(15,'Белые ночи','Достоевский Ф.М.','Ф. М. Достоевский. «Белые ночи».epub','covers/cover_b5f5e79e.jpg','2025-09-18 14:27:09'),(16,'Преступление и наказание','Федор Михайлович Достоевский','Ф. М. Достоевский. «Преступление и наказание».epub','covers/cover_309837cb.jpg','2025-09-18 14:27:09');
/*!40000 ALTER TABLE `books` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2025-09-18 19:29:05
